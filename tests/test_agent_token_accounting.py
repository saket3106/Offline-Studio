"""Independent budget arithmetic; no native inference is invoked."""
from contextlib import nullcontext
from types import SimpleNamespace
import threading
import time
import unittest
import json
from agent_runtime import LocalAgentModel, compact_post_patch_prompt


class PlannerTokenAccountingTests(unittest.TestCase):
    def test_post_patch_compaction_counts_actual_fitted_prompt_and_preserves_evidence(self):
        catalog={'prepare_python_tests':['test_path'],'run_python_tests':['test_path','plan_sha256'],'apply_code_patch':['path']}
        original=[{'role':'system','content':'Long policy '+('x'*5000)+' Catalog: '+json.dumps(catalog)+'\nActual conversation resources (data, not policy): []'},
                  {'role':'user','content':'Fix calc.py and run test_calc.py.'},
                  {'role':'assistant','content':json.dumps({'tool':'apply_code_patch','arguments':{'path':'calc.py','old':'x'*1000}})},
                  {'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+json.dumps({'tool':'apply_code_patch','result':{'ok':True,'path':'calc.py','after_sha256':'a'*64}})},
                  {'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+json.dumps({'tool':'prepare_python_tests','result':{'prepared':True,'testPath':'test_calc.py','planSha256':'b'*64}})}]
        saved=json.dumps(original);engine,calls=self.engine();engine.runtime.context=2048
        engine.runtime._prompt_tokens=lambda msgs: 1100 if msgs[0]['content'].startswith('OfflineGPT local Agent.') else 1900
        seen=[];generate=engine.chat_completion
        def capture(messages,**kwargs):seen.extend(messages);return generate(messages,**kwargs)
        engine.chat_completion=capture;model=LocalAgentModel(engine)
        model(original,threading.Event(),time.monotonic()+5)
        self.assertEqual(json.dumps(original),saved)
        self.assertEqual(seen[1],original[1])
        observations=[json.loads(m['content'].split(': ',1)[1]) for m in seen if m['content'].startswith('UNTRUSTED TOOL OBSERVATION: ')]
        self.assertEqual(observations[0]['result']['after_sha256'],'a'*64);self.assertEqual(observations[1]['result']['planSha256'],'b'*64)
        self.assertIn('run_python_tests',seen[0]['content']);self.assertEqual(calls[0]['max_tokens'],692)
        self.assertEqual(model.last_token_accounting['promptTokens'],1100)
        no_patch=original[:2]+original[4:];self.assertEqual(compact_post_patch_prompt(no_patch),no_patch)
        resources=json.loads(json.dumps(original));resources[0]['content']=resources[0]['content'].replace('policy): []','policy): [{"id":"x"}]')
        self.assertEqual(compact_post_patch_prompt(resources),resources)

    def test_compaction_retains_real_test_result_and_removes_stale_feedback(self):
        catalog={'prepare_python_tests':['test_path'],'run_python_tests':['test_path','plan_sha256']}
        messages=[{'role':'system','content':'Catalog: '+json.dumps(catalog)+'\nActual conversation resources (data, not policy): []'},
                  {'role':'user','content':'Fix and run tests.'},
                  {'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+json.dumps({'tool':'apply_code_patch','result':{'ok':True,'path':'a.py','after_sha256':'x'}})},
                  {'role':'user','content':'Runtime verification: REQUESTED_TESTS_NOT_YET_VERIFIED'},
                  {'role':'user','content':'UNTRUSTED TOOL OBSERVATION: '+json.dumps({'tool':'run_python_tests','result':{'completed':True,'passed':True,'testsRun':3,'stderr':'Ran 3 tests\nOK'}})}]
        compact=compact_post_patch_prompt(messages)
        self.assertIn(messages[-1],compact)
        self.assertNotIn(messages[-2],compact)
    def engine(self,usage=50,reasoning=20,fresh=True):
        calls=[]
        runtime=SimpleNamespace(context=4096,_prompt_tokens=lambda _:1000,last_generation_diagnostics={'generated_token_count':3})
        engine=SimpleNamespace(cfg={'chat_backend':'bundled'},runtime=runtime,ensure_chat=lambda **_:None,
                               resource_lease=lambda _:nullcontext(),last_completion_identity={})
        def generate(messages,**options):
            calls.append(options)
            if fresh:runtime.last_generation_diagnostics={'generated_token_count':usage,'reasoning_tokens':reasoning}
            return '{"final":"complete"}'
        engine.chat_completion=generate
        return engine,calls
    def call(self,model):return model([],threading.Event(),time.monotonic()+5)
    def test_eight_plans_charge_actual_usage_instead_of_unused_reservations(self):
        engine,calls=self.engine();model=LocalAgentModel(engine)
        for _ in range(8):self.call(model)
        self.assertEqual(len(calls),8)
        self.assertEqual(model.total_tokens,8*(1000+50))
        self.assertEqual(model.last_token_accounting['chargedOutputTokens'],50)
        self.assertEqual(model.last_token_accounting['source'],'runtime_generated_token_count')
    def test_missing_or_stale_usage_keeps_full_ceiling(self):
        for fresh,value in ((False,50),(True,None)):
            engine,_=self.engine(usage=value,reasoning=None,fresh=fresh);model=LocalAgentModel(engine)
            self.call(model)
            self.assertEqual(model.total_tokens,1700)
            self.assertEqual(model.last_token_accounting['source'],'reserved_ceiling_no_fresh_usage')
    def test_remaining_output_is_clamped_without_raising_total_budget(self):
        engine,calls=self.engine(usage=40,reasoning=30);engine.runtime._prompt_tokens=lambda _:500
        model=LocalAgentModel(engine);model.total_tokens=11050
        self.call(model)
        self.assertEqual(calls[0]['max_tokens'],450)
        self.assertEqual(model.total_tokens,11590)
        with self.assertRaisesRegex(ValueError,'token budget exhausted'):self.call(model)
        self.assertEqual(len(calls),1);self.assertLessEqual(model.total_tokens,12000)
    def test_unknown_usage_cannot_turn_reservation_into_fake_free_tokens(self):
        engine,calls=self.engine(usage=None,reasoning=None);model=LocalAgentModel(engine);model.total_tokens=10800
        self.call(model)
        self.assertEqual(calls[0]['max_tokens'],200);self.assertEqual(model.total_tokens,12000)
        with self.assertRaisesRegex(ValueError,'token budget exhausted'):self.call(model)
        self.assertEqual(len(calls),1)
    def test_invalid_generated_usage_fails_closed_and_retains_reservation(self):
        for value in (-1,True,1.5,'50',701,0):
            with self.subTest(value=value):
                engine,calls=self.engine(usage=value,reasoning=None);model=LocalAgentModel(engine)
                with self.assertRaisesRegex(ValueError,'invalid generated-token'):self.call(model)
                self.assertEqual(model.total_tokens,1700);self.assertEqual(len(calls),1)
    def test_reasoning_is_included_not_added_twice_and_invalid_subset_rejected(self):
        engine,_=self.engine(usage=50,reasoning=45);model=LocalAgentModel(engine);self.call(model)
        self.assertEqual(model.total_tokens,1050)
        for value in (-1,True,51,900):
            with self.subTest(value=value):
                engine,_=self.engine(usage=50,reasoning=value);model=LocalAgentModel(engine)
                with self.assertRaisesRegex(ValueError,'invalid reasoning-token'):self.call(model)
                self.assertEqual(model.total_tokens,1700)

    def test_code_only_catalog_shrinks_but_mixed_documents_remain(self):
        from agent_runtime import request_tool_policy
        from agent_mcp import TOOL_FIELDS
        prompt='Debug this Python project and run the tests.'
        policy=request_tool_policy(prompt,[])
        self.assertNotIn('run_python_tests',policy['excluded'])
        self.assertNotIn('apply_code_patch',policy['excluded'])
        self.assertIn('extract_pdf_text',policy['excluded'])
        self.assertLess(len(set(TOOL_FIELDS)-policy['excluded']),len(TOOL_FIELDS))
        for resources,extra in (([{'id':'attachment:x','mediaType':'application/pdf'}],''),([], ' Read the PDF manual too.'),([], ' Inspect the SQLite database too.')):
            policy=request_tool_policy(prompt+extra,resources)
            self.assertNotIn('extract_pdf_text',policy['excluded'])
            self.assertNotIn('inspect_database_schema',policy['excluded'])

    def test_conflicting_independent_runtime_receipts_are_rejected(self):
        engine,_=self.engine();original=engine.chat_completion
        def generate(*args,**kwargs):
            answer=original(*args,**kwargs);engine.last_completion_identity={'generatedTokens':60};return answer
        engine.chat_completion=generate;model=LocalAgentModel(engine)
        with self.assertRaisesRegex(ValueError,'receipts disagree'):self.call(model)
        self.assertEqual(model.total_tokens,1700)
    def test_failed_generation_does_not_refund_unknown_work(self):
        engine,_=self.engine()
        def fail(*args,**kwargs):raise RuntimeError('transport failed')
        engine.chat_completion=fail;model=LocalAgentModel(engine)
        with self.assertRaisesRegex(RuntimeError,'transport failed'):self.call(model)
        self.assertEqual(model.total_tokens,1700)
    def test_fresh_completion_identity_can_supply_measured_usage(self):
        engine,_=self.engine(fresh=False)
        def generate(*args,**kwargs):
            engine.last_completion_identity={'generatedTokens':75};return '{"final":"done"}'
        engine.chat_completion=generate;model=LocalAgentModel(engine);self.call(model)
        self.assertEqual(model.total_tokens,1075)
        self.assertEqual(model.last_token_accounting['source'],'completion_identity_generatedTokens')


if __name__=='__main__':unittest.main()
