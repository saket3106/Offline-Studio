"""Real collision policy, without Analysis, model work or global environment writes."""
import json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from in_place_packaging import controlled_build_environment,digest,verify_build_environment
class EnvironmentTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.r=Path(self.tmp.name);self.a=self.r/'Application';self.a.mkdir();(self.a/'Offline GPT.exe').write_bytes(b'old exe');self.base=self.r/'python';(self.base/'DLLs').mkdir(parents=True);self.sdk=self.r/'sdk/Scripts';self.sdk.mkdir(parents=True);self.crt=self.r/'retained-crt';self.crt.mkdir();self.win=self.r/'Windows';(self.win/'System32').mkdir(parents=True);self.poison=self.r/'poppler';self.poison.mkdir();self.entries=[]
  for name,root in [('libssl-3-x64.dll',self.base/'DLLs'),('libcrypto-3-x64.dll',self.base/'DLLs'),('ucrtbase.dll',self.crt),('api-ms-win-crt-runtime-l1-1-0.dll',self.crt)]:
   source=root/name;source.write_bytes(('verified '+name).encode());(self.a/name).write_bytes(source.read_bytes());(self.poison/name).write_bytes(b'wrong same basename');self.entries.append({'name':name,'input':str(source),'inputSha256':digest(source)})
  self.pass_receipt={'status':'PASS','installedExeSha256':digest(self.a/'Offline GPT.exe'),'entries':self.entries}
 def make(self,approved=None):return controlled_build_environment(approved or self.pass_receipt,self.a,self.sdk/'python.exe',self.base,self.win,{'PATH':str(self.poison),'KEEP':'yes'})
 def test_poisoned_inherited_path_is_removed_without_mutating_parent(self):
  before=os.environ.get('PATH');env,evidence=self.make();self.assertNotIn(str(self.poison),env['PATH']);self.assertEqual(env['KEEP'],'yes');self.assertEqual(os.environ.get('PATH'),before);self.assertEqual(len(evidence['pins']),4)
 def test_changed_selected_dll_is_not_replaced_or_accepted(self):
  path=self.base/'DLLs/libssl-3-x64.dll';path.write_bytes(b'changed');original=(self.a/path.name).read_bytes()
  with self.assertRaisesRegex(ValueError,'changed'):self.make()
  self.assertEqual((self.a/path.name).read_bytes(),original)
 def test_ambiguous_crt_origin_and_duplicate_destination_fail(self):
  clone=dict(self.entries[-1]);clone['input']=str(self.poison/clone['name']);clone['inputSha256']=digest(clone['input']);(self.a/clone['name']).write_bytes(Path(clone['input']).read_bytes())
  with self.assertRaisesRegex(ValueError,'Ambiguous'):self.make({**self.pass_receipt,'entries':self.entries[:-1]+[clone]})
  (self.a/clone['name']).write_bytes(Path(self.entries[-1]['input']).read_bytes())
  with self.assertRaisesRegex(ValueError,'Duplicate'):self.make({**self.pass_receipt,'entries':self.entries+[self.entries[0]]})
 def test_failed_or_other_exe_receipt_cannot_authorize_paths(self):
  for receipt in [{**self.pass_receipt,'status':'FAIL'},{**self.pass_receipt,'installedExeSha256':'0'*64}]:
   with self.assertRaisesRegex(ValueError,'PASS'):self.make(receipt)
 def test_analysis_base_and_accepted_compiled_output_are_distinct_authorities(self):
  prior={**self.pass_receipt,'installedExeSha256':'0'*64};compiled={'exeSha256':digest(self.a/'Offline GPT.exe'),'compiledCanonicalModules':['app'],'compiledScripts':['app']}
  _,record=controlled_build_environment(prior,self.a,self.sdk/'python.exe',self.base,self.win,{},compiled)
  self.assertNotEqual(record['installedExeSha256'],record['inputReceiptBaseExeSha256']);self.assertEqual(prior['installedExeSha256'],'0'*64)
  with self.assertRaisesRegex(ValueError,'PASS'):controlled_build_environment(prior,self.a,self.sdk/'python.exe',self.base,self.win,{},dict(compiled,exeSha256='1'*64))
 def test_actual_environment_and_authority_are_checked_before_analysis(self):
  env,evidence=self.make();prior=self.r/'prior.json';prior.write_text(json.dumps(self.pass_receipt));receipt=self.r/'env.json';receipt.write_text(json.dumps({'priorCompatibilityReceipt':str(prior),'priorCompatibilitySha256':digest(prior),'interpreter':str(self.sdk/'python.exe'),'basePrefix':str(self.base),'systemRoot':str(self.win),'environment':evidence}))
  with patch.dict(os.environ,{'PATH':env['PATH']}):self.assertEqual(verify_build_environment(receipt,self.a),evidence)
  with patch.dict(os.environ,{'PATH':str(self.poison)}):
   with self.assertRaisesRegex(ValueError,'Actual build'):verify_build_environment(receipt,self.a)
  prior.write_text('{}')
  with self.assertRaisesRegex(ValueError,'authority'):verify_build_environment(receipt,self.a)
if __name__=='__main__':unittest.main()
