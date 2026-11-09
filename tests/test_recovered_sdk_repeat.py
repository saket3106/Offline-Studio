"""A prior relocation needs its original build/approval chain, not a new alias."""
from pathlib import Path
import copy,json,os,subprocess,tempfile,unittest
import in_place_packaging as p
from tests import test_native_pin_lineage as lineage_fixture


class RecoveredRepeatTests(unittest.TestCase):
 def fixture(self,root):
  a,new,old,historical,previous,fresh,path,c,approved=lineage_fixture.RepeatPinLineage('test_repeat_pin_accepts_only_the_previously_reviewed_sdk_origin').fixture(root)
  recovered=root/'recovered.dll';recovered.write_bytes(new.read_bytes())
  entry={'destination':'fixture.dll','originalInput':str(new),'recoveredInput':str(recovered),'sha256':p.digest(new),'authenticode':dict(historical['pairs'][0]['buildAuthenticode'],Path=str(recovered))}
  prior_compat=root/'prior-compat.json';prior_compat.write_text(json.dumps({'status':'PASS','nativeInputPins':{'sha256':'a'*64}}))
  historical_approval=root/'historical-relocation.json'
  historical_approval.write_text(json.dumps({'purpose':'OWNER_APPROVED_EXACT_ORIGINAL_RELOCATION','ownerApproval':'explicit historical fixture authorization','installedExeSha256':historical['installedExeSha256'],'historicalProofSha256':'a'*64,'entries':[entry]}))
  prior_binding=root/'prior-binding.json';prior_binding.write_text(json.dumps({'exeSha256':historical['installedExeSha256'],'nativeInputPinReceipt':str(previous),'nativeInputPinSha256':p.digest(previous),'originalInputRelocationReceipt':str(historical_approval),'originalInputRelocationSha256':p.digest(historical_approval)}))
  env=root/'historical-env.json';env.write_text(json.dumps({'priorCompiledReceipt':str(prior_binding),'priorCompiledSha256':p.digest(prior_binding),'priorCompatibilityReceipt':str(prior_compat),'priorCompatibilitySha256':p.digest(prior_compat)}))
  current_approval=root/'current-relocation.json';current_approval.write_text(json.dumps({'purpose':'OWNER_APPROVED_EXACT_ORIGINAL_RELOCATION','ownerApproval':'reuse unchanged explicit historical mapping','installedExeSha256':c['exeSha256'],'historicalProofSha256':approved['nativeInputPins']['sha256'],'entries':[copy.deepcopy(entry)]}))
  c.update(originalInputRelocationReceipt=str(current_approval),originalInputRelocationSha256=p.digest(current_approval),historicalBuildEnvironmentReceipt=str(env),historicalBuildEnvironmentSha256=p.digest(env))
  fresh['authorityReceipts'].append({'path':str(env),'sha256':p.digest(env)})
  lineage_fixture.RepeatPinLineage().save(fresh,path,c)
  approved['nativeInputPins']['entries'][0].update(analysisInput=str(recovered),discoveredInput=str(new))
  return a,new,old,recovered,approved,c,fresh,path,env,prior_binding,historical_approval,current_approval

 def check(self,values):return p.native_pin_inputs(values[4],values[0],values[5])

 def test_recovered_path_retains_original_raw_bytes_and_payload(self):
  with tempfile.TemporaryDirectory() as d:
   v=self.fixture(Path(d));v[1].write_bytes(b'later SDK signing version is not reused')
   pins=self.check(v);self.assertEqual(pins[0]['buildInput'],str(v[3]));self.assertEqual(pins[0]['installedInput'],str(v[2]))

 def test_recovered_discovery_and_lexical_windows_path_are_supported(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);v=self.fixture(root);(root/'empty').mkdir()
   v[4]['nativeInputPins']['entries'][0].update(analysisInput=str(root/'empty/../recovered.dll'),discoveredInput=str(v[3]))
   self.assertEqual(len(self.check(v)),1)

 def test_unauthorized_same_byte_origin_or_discovery_is_rejected(self):
  for field in ('analysisInput','discoveredInput'):
   with self.subTest(field=field),tempfile.TemporaryDirectory() as d:
    root=Path(d);v=self.fixture(root);alias=root/'unapproved.dll';alias.write_bytes(v[3].read_bytes())
    v[4]['nativeInputPins']['entries'][0][field]=str(alias)
    with self.assertRaises(ValueError):self.check(v)

 def test_fresh_relocation_cannot_rewrite_historical_approval(self):
  for change in ('path','signer','hash','unapproved_file'):
   with self.subTest(change=change),tempfile.TemporaryDirectory() as d:
    root=Path(d);v=self.fixture(root);receipt=json.loads(v[11].read_text());item=receipt['entries'][0]
    if change=='signer':item['authenticode']['Thumbprint']='unapproved signer'
    elif change=='hash':item['sha256']='f'*64
    else:
     alias=root/'new-origin.dll';alias.write_bytes(v[3].read_bytes());item['recoveredInput']=str(alias);item['authenticode']['Path']=str(alias)
     if change=='unapproved_file':alias.write_bytes(b'different file')
    v[11].write_text(json.dumps(receipt));v[5]['originalInputRelocationSha256']=p.digest(v[11])
    with self.assertRaises(ValueError):self.check(v)

 def test_recovered_raw_hash_mismatch_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   v=self.fixture(Path(d));v[3].write_bytes(b'tampered')
   with self.assertRaisesRegex(ValueError,'raw identity'):self.check(v)

 def test_original_approval_or_build_binding_tamper_is_rejected(self):
  for index in (8,9,10):
   with self.subTest(index=index),tempfile.TemporaryDirectory() as d:
    v=self.fixture(Path(d));v[index].write_text('{}')
    with self.assertRaises(ValueError):self.check(v)

 def test_missing_original_environment_authority_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   v=self.fixture(Path(d));v[6]['authorityReceipts'].pop();lineage_fixture.RepeatPinLineage().save(v[6],v[7],v[5])
   with self.assertRaisesRegex(ValueError,'authority'):self.check(v)

 @unittest.skipUnless(os.name=='nt','Actual Windows junction guard')
 def test_junction_alias_is_rejected_before_resolution(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);v=self.fixture(root);link=root/'junction'
   subprocess.run(['cmd','/c','mklink','/J',str(link),str(root/'sdk')],check=True,capture_output=True)
   try:
    v[4]['nativeInputPins']['entries'][0]['analysisInput']=str(link/'fixture.dll')
    with self.assertRaisesRegex(ValueError,'Redirected'):self.check(v)
   finally:os.rmdir(link)


if __name__=='__main__':unittest.main()
