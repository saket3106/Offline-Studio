"""Authored, disposable unittest projects. No native models or user code is run."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from agent_mcp import (WorkspaceTools, MCPClientManager, APPROVAL_TOOLS, validate_arguments,
                       TEST_EXECUTION_WARNING, capability_catalog)
from agent_permissions import ApprovalBroker, GrantAuthority
from agent_runtime import (AgentRuntime, execution_evidence_findings, is_same_objective_recovered,
                           request_tool_policy)
from agent_workspace import WorkspaceAccess


class ApprovedExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='offlinegpt-authored-test-')
        self.root=Path(self.temp.name)/'project';self.root.mkdir()
        self.access=WorkspaceAccess(self.root);self.grants=GrantAuthority(b'x'*32)
        self.tools=WorkspaceTools(self.access,self.grants)
        self.write('calculator.py','def multiply(a,b):\n    return a*b-1\n')
        self.write('test_calculator.py','import unittest\nfrom calculator import multiply\nclass Arithmetic(unittest.TestCase):\n    def test_product(self): self.assertEqual(multiply(19,23),437)\n')
    def tearDown(self):
        self.access.close();self.temp.cleanup()
    def write(self,path,data):
        destination=self.root/path;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_text(data,encoding='utf-8')
    def plan(self,path='test_calculator.py'):
        plan=self.tools.call('prepare_python_tests',{'test_path':path})
        return {'test_path':path,'plan_sha256':plan['planSha256']}
    def approved(self,tool,args):
        return self.tools.call(tool,args,self.grants.issue(tool,args))
    def test_real_fail_repair_and_pass_with_unchanged_test(self):
        before=(self.root/'test_calculator.py').read_bytes();args=self.plan()
        failed=self.approved('run_python_tests',args)
        self.assertFalse(failed['passed']);self.assertEqual(failed['testsRun'],1)
        self.assertNotEqual(failed['exitCode'],0);self.assertEqual(failed['failures'],1)
        patch_args={'path':'calculator.py','old':'return a*b-1','new':'return a*b',
                    'expected_sha256':hashlib.sha256((self.root/'calculator.py').read_bytes()).hexdigest()}
        preview=self.tools.preview('apply_code_patch',patch_args)
        self.assertIn('-    return a*b-1',preview['diff'])
        receipt=self.approved('apply_code_patch',patch_args)
        self.assertTrue(receipt['ok']);self.assertTrue((self.root/receipt['backup_file']).is_file())
        with self.assertRaises(PermissionError):self.approved('run_python_tests',args)
        passed=self.approved('run_python_tests',self.plan())
        self.assertTrue(passed['passed'],passed);self.assertEqual(passed['testsRun'],1)
        self.assertEqual(passed['exitCode'],0);self.assertTrue(passed['descendantCleanupVerified'])
        self.assertFalse(passed['securitySandbox']);self.assertEqual((self.root/'test_calculator.py').read_bytes(),before)
        self.assertTrue(is_same_objective_recovered({'tool':'run_python_tests','result':failed},[{'tool':'run_python_tests','result':passed}],[]))
    def test_missing_approval_and_exact_argument_binding(self):
        args=self.plan()
        with self.assertRaises(PermissionError):self.tools.call('run_python_tests',args)
        grant=self.grants.issue('run_python_tests',args)
        with self.assertRaises(PermissionError):self.tools.call('run_python_tests',dict(args,timeout_seconds='1'),grant)
        # A rejected substitution did not change the approved identity or execute code.
        result=self.tools.call('run_python_tests',args,grant)
        self.assertEqual(result['testsRun'],1)
        with self.assertRaises(PermissionError):self.tools.call('run_python_tests',args,grant)
    def test_preview_requires_fresh_plan_and_discloses_true_boundary(self):
        args=self.plan();preview=self.tools.preview('run_python_tests',args)
        self.assertEqual(preview['executionWarning'],TEST_EXECUTION_WARNING)
        self.assertIn('NOT A SECURITY SANDBOX',preview['executionWarning'])
        self.assertIn('network',preview['executionWarning']);self.assertEqual(len(preview['files']),2)
        self.write('calculator.py','changed = True\n')
        with self.assertRaises(PermissionError):self.tools.preview('run_python_tests',args)
    def test_no_custom_commands_or_invalid_identities(self):
        for extra in ({'command':'whoami'},{'argv':'-c pass'},{'cwd':'C:/'}):
            with self.assertRaises(ValueError):validate_arguments('run_python_tests',dict(self.plan(),**extra))
        for seconds in ('0','9','-1','1.5','nan'):
            with self.assertRaises(ValueError):validate_arguments('run_python_tests',dict(self.plan(),timeout_seconds=seconds))
        with self.assertRaises(ValueError):validate_arguments('run_python_tests',{'test_path':'x.py','plan_sha256':'invented'})
    def test_no_empty_skipped_or_early_exit_false_pass(self):
        for body in ('x=1\n',"import unittest\n@unittest.skip('not implemented')\nclass Skip(unittest.TestCase):\n def test_skip(self): pass\n",'import os\nos._exit(0)\n'):
            self.write('test_empty.py',body)
            result=self.approved('run_python_tests',self.plan('test_empty.py'))
            self.assertFalse(result['passed'],result);self.assertIn('error',result)
    def test_timeout_and_descendant_cleanup(self):
        self.write('test_wait.py','import unittest,time\nclass Wait(unittest.TestCase):\n def test_wait(self): time.sleep(20)\n')
        result=self.approved('run_python_tests',dict(self.plan('test_wait.py'),timeout_seconds='1'))
        self.assertTrue(result['timedOut'],result);self.assertFalse(result['passed']);self.assertTrue(result['descendantCleanupVerified'])
    def test_child_processes_do_not_survive_successful_primary(self):
        self.write('test_child.py',"import unittest,subprocess,sys\nclass Child(unittest.TestCase):\n def test_spawn(self):\n  subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])\n  self.assertTrue(True)\n")
        result=self.approved('run_python_tests',self.plan('test_child.py'))
        self.assertTrue(result['passed'],result);self.assertTrue(result['descendantCleanupVerified'])
    def test_snapshot_excludes_private_files_and_never_runs_original_cwd(self):
        self.write('secrets/token.py','raise RuntimeError("never execute")')
        self.write('test_cwd.py',"import unittest\nfrom pathlib import Path\nclass Cwd(unittest.TestCase):\n def test_write(self):\n  Path('temporary-test-output.txt').write_text('fixture')\n  self.assertTrue(True)\n")
        result=self.approved('run_python_tests',self.plan('test_cwd.py'))
        self.assertTrue(result['passed'],result)
        self.assertFalse((self.root/'temporary-test-output.txt').exists())
    def test_selected_test_folder_requires_no_package_initializer(self):
        self.write('tests/test_nested.py','import unittest\nclass Nested(unittest.TestCase):\n def test_one(self): self.assertEqual(2+2,4)\n')
        result=self.approved('run_python_tests',self.plan('tests/test_nested.py'))
        self.assertTrue(result['passed'],result)
    def test_output_is_bounded_and_reports_limit(self):
        self.write('test_output.py',"import unittest,os\nclass Output(unittest.TestCase):\n def test_print(self):\n  for n in range(300): os.write(1,b'x'*4096)\n")
        result=self.approved('run_python_tests',self.plan('test_output.py'))
        self.assertFalse(result['passed']);self.assertTrue(result['outputLimitReached'])
        self.assertLessEqual(len(result['stdout'].encode()),12000)
        self.assertTrue(result['descendantCleanupVerified'])
    def test_failed_patch_and_stale_source_never_overwrite(self):
        old=(self.root/'calculator.py').read_bytes()
        args={'path':'calculator.py','old':'return a*b-1','new':'return a*b','expected_sha256':'0'*64}
        with self.assertRaises(PermissionError):self.approved('apply_code_patch',args)
        self.assertEqual((self.root/'calculator.py').read_bytes(),old)
        args['expected_sha256']=hashlib.sha256(old).hexdigest();args['old']='missing'
        with self.assertRaises(ValueError):self.approved('apply_code_patch',args)
        self.assertEqual((self.root/'calculator.py').read_bytes(),old)
    def test_catalog_and_readonly_requests_do_not_advertise_execution(self):
        catalog=capability_catalog()
        self.assertIn('NOT sandboxed',catalog['run_python_tests']['permission'])
        self.assertIn('run_python_tests',request_tool_policy('Explain what unit tests do',[])['excluded'])
        self.assertNotIn('run_python_tests',request_tool_policy('Repair this project and run the tests',[])['excluded'])
    def test_true_mcp_transport_runs_authored_fixture(self):
        async def run():
            async with MCPClientManager(self.root,interpreter=sys.executable) as client:
                plan=await client.call('prepare_python_tests',{'test_path':'test_calculator.py'})
                args={'test_path':'test_calculator.py','plan_sha256':plan['planSha256']}
                with self.assertRaises(PermissionError):await client.call('run_python_tests',args)
                return await client.call('run_python_tests',args,approved=True)
        result=asyncio.run(run())
        self.assertEqual(result['testsRun'],1);self.assertFalse(result['passed'])
        self.assertTrue(result['descendantCleanupVerified'])



    def test_runtime_cancellation_cleans_actual_test_processes(self):
        import psutil,time
        self.write('test_cancel.py','import unittest,time\nclass Cancel(unittest.TestCase):\n def test_wait(self): time.sleep(20)\n')
        broker=ApprovalBroker();running=threading.Event();observed=set();seen={}
        def notify(event):
            request=event.get('approval')
            if request:broker.decide(event['taskId'],request['requestId'],request['digest'],True)
            if event.get('state')=='EXECUTING_TOOL' and event.get('tool')=='run_python_tests':running.set()
        def model(messages,*_):
            for message in messages:
                prefix='UNTRUSTED TOOL OBSERVATION: '
                if message.get('content','').startswith(prefix):
                    value=json.loads(message['content'][len(prefix):])
                    if value['tool']=='prepare_python_tests':seen['plan']=value['result']['planSha256']
            if 'plan' not in seen:return json.dumps({'tool':'prepare_python_tests','arguments':{'test_path':'test_cancel.py'}})
            return json.dumps({'tool':'run_python_tests','arguments':{'test_path':'test_cancel.py','plan_sha256':seen['plan']}})
        runtime=AgentRuntime(model,self.root,None,'cancel-fixture',notify,broker=broker,interpreter=sys.executable)
        async def go():
            task=asyncio.create_task(runtime.run('Run the selected tests.'))
            deadline=time.monotonic()+4
            while not running.is_set() and time.monotonic()<deadline:await asyncio.sleep(.02)
            self.assertTrue(running.is_set())
            await asyncio.sleep(.3)
            observed.update(psutil.Process().children(recursive=True))
            started=time.monotonic();runtime.cancel();result=await asyncio.wait_for(task,5)
            self.assertLess(time.monotonic()-started,5)
            return result
        result=asyncio.run(go())
        self.assertEqual(runtime.state,'CANCELED',result)
        self.assertFalse([p.pid for p in observed if p.is_running()])

    def test_runtime_rejects_missing_and_stale_plans_then_accepts_fresh_plan(self):
        for stale in (False, True):
            with self.subTest(stale=stale):
                self.write('calculator.py','def multiply(a,b):\n    return a*b\n')
                broker=ApprovalBroker();events=[];stage=[];seen={};changed=[False]
                def notify(event):
                    events.append(event)
                    if stale and not changed[0] and event.get('state')=='PROCESSING_RESULT' and event.get('tool')=='prepare_python_tests':
                        self.write('calculator.py','def multiply(a,b):\n    return a*b # revised\n');changed[0]=True
                    request=event.get('approval')
                    if request:self.assertTrue(broker.decide(event['taskId'],request['requestId'],request['digest'],True))
                def model(messages,*_):
                    for message in messages:
                        prefix='UNTRUSTED TOOL OBSERVATION: '
                        content=message.get('content','')
                        if content.startswith(prefix) and content.endswith('}'):
                            value=json.loads(content[len(prefix):])
                            if value['tool']=='prepare_python_tests':seen['plan']=value['result']['planSha256']
                    index=len(stage);stage.append(index)
                    if stale and index==0 or not stale and index==1 or stale and index==2:
                        return json.dumps({'tool':'prepare_python_tests','arguments':{'test_path':'test_calculator.py'}})
                    if index==(1 if stale else 0):
                        return json.dumps({'tool':'run_python_tests','arguments':{'test_path':'test_calculator.py','plan_sha256':seen.get('plan','0'*64)}})
                    if index==(3 if stale else 2):
                        return json.dumps({'tool':'run_python_tests','arguments':{'test_path':'test_calculator.py','plan_sha256':seen['plan']}})
                    return json.dumps({'final':'The unchanged test passed.'})
                runtime=AgentRuntime(model,self.root,None,'plan-fixture',notify,broker=broker,interpreter=sys.executable)
                answer=asyncio.run(runtime.run('Run the tests.'))
                self.assertEqual(runtime.state,'COMPLETED',answer)
                rejected=[t for t in runtime.traces if t['status']=='rejected']
                self.assertEqual(len(rejected),1)
                self.assertEqual(rejected[0]['output']['code'],'TEST_PLAN_REQUIRED_OR_STALE')
                self.assertFalse(rejected[0]['output']['dispatched'])
                self.assertEqual(sum(e['state']=='AWAITING_APPROVAL' for e in events),1)
                self.assertTrue(next(t for t in runtime.traces if t['tool']=='run_python_tests' and t['status']=='completed')['output']['passed'])

    def test_full_default_budget_agent_repair_with_real_mcp_and_test_processes(self):
        broker=ApprovalBroker();events=[];calls=[];seen={}
        def notify(event):
            events.append(event)
            approval=event.get('approval')
            if approval:
                self.assertTrue(broker.decide(event['taskId'],approval['requestId'],approval['digest'],True))
        def model(messages,cancel,deadline):
            observations=[]
            for message in messages:
                content=message.get('content','')
                prefix='UNTRUSTED TOOL OBSERVATION: '
                if content.startswith(prefix):observations.append(json.loads(content[len(prefix):]))
            if observations:
                last=observations[-1]
                if last['tool']=='prepare_python_tests':seen['plan']=last['result']['planSha256']
                if last['tool']=='prepare_code_patch':seen['source']=last['result']['sourceSha256']
            stage=len(calls)
            actions=[
                {'tool':'inspect_source_code','arguments':{'path':'calculator.py'}},
                {'tool':'prepare_python_tests','arguments':{'test_path':'test_calculator.py'}},
                {'tool':'run_python_tests','arguments':{'test_path':'test_calculator.py','plan_sha256':seen.get('plan','0'*64)}},
                {'tool':'prepare_code_patch','arguments':{'path':'calculator.py','old':'return a*b-1','new':'return a*b'}},
                {'tool':'apply_code_patch','arguments':{'path':'calculator.py','old':'return a*b-1','new':'return a*b','expected_sha256':seen.get('source','0'*64)}},
                {'tool':'prepare_python_tests','arguments':{'test_path':'test_calculator.py'}},
                {'tool':'run_python_tests','arguments':{'test_path':'test_calculator.py','plan_sha256':seen.get('plan','0'*64)}},
                {'final':'I fixed the code. The unchanged test now passed: 19 times 23 is 437.'},
            ]
            calls.append(stage)
            return json.dumps(actions[stage])
        runtime=AgentRuntime(model,self.root,None,'authored-fixture',notify,broker=broker,interpreter=sys.executable)
        result=asyncio.run(runtime.run('Debug the Python code in this project and run the tests.'))
        self.assertEqual(runtime.state,'COMPLETED',result)
        self.assertEqual(runtime.step,8);self.assertEqual(len(calls),8)
        self.assertEqual(sum(e['state']=='AWAITING_APPROVAL' for e in events),3)
        results=[t['output'] for t in runtime.traces if t['tool']=='run_python_tests']
        self.assertEqual([r['passed'] for r in results],[False,True])
        self.assertEqual([r['testsRun'] for r in results],[1,1])
        self.assertEqual((self.root/'calculator.py').read_text(encoding='utf-8'),'def multiply(a,b):\n    return a*b\n')

    def test_post_patch_feedback_enables_model_driven_test_continuation(self):
        broker=ApprovalBroker();events=[];seen={};calls=[]
        def notify(event):
            events.append(event)
            request=event.get('approval')
            if request:self.assertTrue(broker.decide(event['taskId'],request['requestId'],request['digest'],True))
        def model(messages,*_):
            for message in messages:
                content=message.get('content','');prefix='UNTRUSTED TOOL OBSERVATION: '
                if content.startswith(prefix) and content.endswith('}'):
                    obs=json.loads(content[len(prefix):])
                    if obs['tool']=='prepare_code_patch':seen['source']=obs['result']['sourceSha256']
                    if obs['tool']=='prepare_python_tests':seen['plan']=obs['result']['planSha256']
                    if obs['tool']=='run_python_tests':seen['result']=obs['result']
            stage=len(calls);calls.append(stage)
            patch_args={'path':'calculator.py','old':'return a*b-1','new':'return a*b'}
            if stage==0:return json.dumps({'tool':'inspect_source_code','arguments':{'path':'calculator.py'}})
            if stage==1:return json.dumps({'tool':'prepare_code_patch','arguments':patch_args})
            if stage==2:return json.dumps({'tool':'apply_code_patch','arguments':dict(patch_args,expected_sha256=seen['source'])})
            feedback='\n'.join(m['content'] for m in messages if m['content'].startswith('Runtime verification:'))
            if stage==3:
                self.assertIn('REQUESTED_TESTS_NOT_YET_VERIFIED',feedback)
                self.assertIn('prepare_python_tests',feedback);self.assertIn('run_python_tests',feedback);self.assertIn('plan_sha256',feedback)
                return json.dumps({'final':'The tests passed.'})
            if stage==4:
                self.assertIn('EXECUTION_EVIDENCE_MISSING',feedback)
                return json.dumps({'tool':'prepare_python_tests','arguments':{'test_path':'test_calculator.py'}})
            if stage==5:return json.dumps({'tool':'run_python_tests','arguments':{'test_path':'test_calculator.py','plan_sha256':seen['plan']}})
            self.assertTrue(seen['result']['passed'])
            return json.dumps({'final':'I fixed calculator.py and the unchanged test passed.'})
        runtime=AgentRuntime(model,self.root,None,'post-patch-fixture',notify,broker=broker,interpreter=sys.executable)
        answer=asyncio.run(runtime.run('Debug the Python code and run the tests.'))
        self.assertEqual(runtime.state,'COMPLETED',answer)
        self.assertEqual(len(calls),7)
        self.assertEqual(sum(e['state']=='AWAITING_APPROVAL' for e in events),2)
        self.assertEqual(seen['result']['testsRun'],1)


class ExecutionEvidenceTests(unittest.TestCase):
    def test_claimed_test_pass_requires_actual_nonempty_exit_and_cleanup(self):
        for result in ({},{'passed':True,'exitCode':0,'testsRun':0,'descendantCleanupVerified':True},
                       {'passed':True,'exitCode':1,'testsRun':1,'descendantCleanupVerified':True},
                       {'passed':True,'exitCode':0,'testsRun':1,'descendantCleanupVerified':False}):
            self.assertTrue(execution_evidence_findings('Review the script','All tests passed.',[{'tool':'run_python_tests','result':result}]))
        result={'passed':True,'exitCode':0,'testsRun':1,'descendantCleanupVerified':True}
        self.assertFalse(execution_evidence_findings('Run tests','All tests passed.',[{'tool':'run_python_tests','result':result}]))
    def test_proposed_patch_is_not_an_applied_write(self):
        self.assertTrue(execution_evidence_findings('Fix source','I fixed the code.',[{'tool':'prepare_code_patch','result':{'applied':False}}]))

    def test_honest_untested_statement_is_not_a_false_pass_claim(self):
        self.assertFalse(execution_evidence_findings('Inspect source','No tests passed because none were executed.',[]))
        self.assertFalse(execution_evidence_findings('Inspect source','I cannot say all tests passed.',[]))
    def test_explanatory_and_negative_execution_requests_stay_readonly(self):
        for prompt in ('How do I run tests?', 'Explain how to run the tests.', 'Fix the file but do not run tests.'):
            self.assertIn('run_python_tests',request_tool_policy(prompt,[])['excluded'])
            self.assertFalse(execution_evidence_findings(prompt,'No tests were executed.',[]))

    def test_changed_test_does_not_reconcile_a_failure(self):
        failure={'tool':'run_python_tests','result':{'testSourceSha256':'a','path':'test_x.py'}}
        passed={'tool':'run_python_tests','result':{'testSourceSha256':'b','path':'test_x.py','passed':True,'exitCode':0,'testsRun':1}}
        self.assertFalse(is_same_objective_recovered(failure,[passed],[]))


if __name__=='__main__':unittest.main()
