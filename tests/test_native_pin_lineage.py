"""Repeat-build native origin lineage; synthetic signed-PE fixtures, never executed."""
from pathlib import Path
import copy,json,tempfile,types,unittest
from unittest.mock import patch
import in_place_packaging as p
try:
 from . import test_native_input_pins as original_pins
except ImportError:
 import test_native_input_pins as original_pins

class RepeatPinLineage(unittest.TestCase):
 def test_owner_approved_original_relocation_preserves_raw_identity_and_signer(self):
  for mutation in ('none','bytes','signer','scope','receipt','origin'):
   with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as d:
    root=Path(d);a,new,old,_,_,fresh,path,c,approved=self.fixture(root)
    recovered=root/'recovered.dll';recovered.write_bytes(new.read_bytes())
    entry={'destination':'fixture.dll','originalInput':str(new),'recoveredInput':str(recovered),'sha256':p.digest(new),'authenticode':dict(fresh['pairs'][0]['buildAuthenticode'],Path=str(recovered))}
    review={'purpose':'OWNER_APPROVED_EXACT_ORIGINAL_RELOCATION','ownerApproval':'synthetic explicit owner decision','installedExeSha256':c['exeSha256'],'historicalProofSha256':approved['nativeInputPins']['sha256'],'entries':[entry]}
    if mutation=='bytes':recovered.write_bytes(b'changed')
    if mutation=='signer':entry['authenticode']['Thumbprint']='different'
    if mutation=='scope':review['entries']=[]
    if mutation=='origin':entry['originalInput']=str(root/'unapproved.dll')
    receipt=root/'relocation.json';receipt.write_text(json.dumps(review));c.update(originalInputRelocationReceipt=str(receipt),originalInputRelocationSha256=p.digest(receipt))
    if mutation=='receipt':receipt.write_text('{}')
    if mutation=='none':
     new.write_bytes(b'new SDK signing variant must not be selected')
     pins=p.native_pin_inputs(approved,a,c)
     self.assertEqual(pins[0]['buildInput'],str(recovered));self.assertEqual(pins[0]['historicalBuildInput'],str(new));self.assertEqual(p.digest(old),pins[0]['installedSha256'])
     prior=root/'prior.json';prior.write_text(json.dumps(approved));binding=root/'binding.json';binding.write_text(json.dumps(c));env=root/'env.json';env.write_text(json.dumps({'priorCompatibilityReceipt':str(prior),'priorCompiledReceipt':str(binding)}))
     analysis=types.SimpleNamespace(binaries=[('fixture.dll',str(new),'BINARY')])
     with patch.object(p,'verify_build_environment'):p.pin_analysis_native_inputs(analysis,a,env)
     self.assertEqual(analysis.binaries,[('fixture.dll',str(old),'BINARY')]);self.assertEqual(analysis._offlinegpt_native_pins['entries'][0]['analysisInput'],str(recovered))
    else:
     with self.assertRaises(ValueError):p.native_pin_inputs(approved,a,c)
 def fixture(self,root):
  a,new,old,historical,path,compiled,approved=original_pins.NativePins('test_valid_explicit_pair').fixture(root)
  previous=root/'historical-proof.json';previous.write_text(json.dumps(historical));previous_sha=p.digest(previous)
  approved.update(status='PASS',installedExeSha256=historical['installedExeSha256'])
  approved['entries'][0]['input']=str(old)
  approved['nativeInputPins']={'receipt':str(previous),'sha256':previous_sha,'entries':[{'name':'fixture.dll','analysisInput':str(new),'pinnedInput':str(old),'installedSha256':p.digest(old)}]}
  (a/'Offline GPT.exe').write_bytes(b'new accepted installed fixture, never executable')
  fresh=copy.deepcopy(historical);fresh['installedExeSha256']=p.digest(a/'Offline GPT.exe');fresh['authorityReceipts'].append({'path':str(previous),'sha256':previous_sha})
  compiled['exeSha256']=fresh['installedExeSha256'];self.save(fresh,path,compiled)
  return a,new,old,historical,previous,fresh,path,compiled,approved
 def save(self,proof,path,compiled):path.write_text(json.dumps(proof));compiled['nativeInputPinSha256']=p.digest(path)
 def test_repeat_pin_accepts_only_the_previously_reviewed_sdk_origin(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,old,_,_,_,_,c,approved=self.fixture(Path(d));result=p.native_pin_inputs(approved,a,c)
   self.assertEqual(len(result),1);self.assertEqual(result[0]['installedInput'],str(old))
 def test_repeat_analysis_keeps_the_installed_raw_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a,new,old,_,_,_,_,c,approved=self.fixture(root)
   prior=root/'prior.json';prior.write_text(json.dumps(approved));binding=root/'compiled.json';binding.write_text(json.dumps(c));env=root/'environment.json';env.write_text(json.dumps({'priorCompatibilityReceipt':str(prior),'priorCompiledReceipt':str(binding)}))
   analysis=types.SimpleNamespace(binaries=[('fixture.dll',str(new),'BINARY')])
   with patch.object(p,'verify_build_environment'):p.pin_analysis_native_inputs(analysis,a,env)
   self.assertEqual(analysis.binaries,[('fixture.dll',str(old),'BINARY')])
 def test_second_repeat_preserves_the_entire_hash_bound_lineage(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a,_,_,_,_,fresh,path,c,approved=self.fixture(root)
   self.assertEqual(len(p.native_pin_inputs(approved,a,c)),1)
   approved['installedExeSha256']=fresh['installedExeSha256']
   approved['nativeInputPins'].update(receipt=str(path),sha256=p.digest(path))
   (a/'Offline GPT.exe').write_bytes(b'third accepted installed fixture')
   third=copy.deepcopy(fresh);third['installedExeSha256']=p.digest(a/'Offline GPT.exe')
   third['authorityReceipts'].append({'path':str(path),'sha256':p.digest(path)})
   next_path=root/'next-proof.json';c.update(exeSha256=third['installedExeSha256'],nativeInputPinReceipt=str(next_path));self.save(third,next_path,c)
   self.assertEqual(len(p.native_pin_inputs(approved,a,c)),1)
 def test_prior_analysis_may_have_already_selected_the_exact_installed_origin(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,old,_,_,_,_,c,approved=self.fixture(Path(d));approved['nativeInputPins']['entries'][0]['analysisInput']=str(old)
   self.assertEqual(len(p.native_pin_inputs(approved,a,c)),1)
 def test_kind_cannot_change_between_accepted_and_current_inputs(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,_,_,_,fresh,path,c,approved=self.fixture(Path(d));fresh['pairs'][0]['kind']='EXTENSION';self.save(fresh,path,c)
   with self.assertRaisesRegex(ValueError,'outside prior'):p.native_pin_inputs(approved,a,c)
 def test_missing_repeat_lineage_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,_,_,_,_,_,c,approved=self.fixture(Path(d));approved.pop('nativeInputPins')
   with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_changed_historical_proof_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,_,_,previous,_,_,c,approved=self.fixture(Path(d));previous.write_text('{}')
   with self.assertRaisesRegex(ValueError,'authority changed|lineage'):p.native_pin_inputs(approved,a,c)
 def test_missing_fresh_authority_link_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,_,_,_,fresh,path,c,approved=self.fixture(Path(d));fresh['authorityReceipts']=fresh['authorityReceipts'][:1];self.save(fresh,path,c)
   with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_missing_or_duplicate_lineage_destination_rejected(self):
  for op in ('missing','duplicate'):
   with self.subTest(op=op),tempfile.TemporaryDirectory() as d:
    a,_,_,_,_,_,_,c,approved=self.fixture(Path(d))
    approved['nativeInputPins']['entries']=[] if op=='missing' else approved['nativeInputPins']['entries']*2
    with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_identical_byte_alias_does_not_grant_an_origin(self):
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);a,new,_,_,_,fresh,path,c,approved=self.fixture(root);alias=root/'alias.dll';alias.write_bytes(new.read_bytes())
   fresh['pairs'][0]['buildInput']=str(alias);fresh['pairs'][0]['buildAuthenticode']['Path']=str(alias);self.save(fresh,path,c)
   with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_lineage_analysis_or_installed_path_change_rejected(self):
  for key in ('analysisInput','pinnedInput','installedSha256'):
   with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
    a,_,_,_,_,_,_,c,approved=self.fixture(Path(d));approved['nativeInputPins']['entries'][0][key]='forged'
    with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_historical_exe_must_match_the_accepted_analysis_input(self):
  with tempfile.TemporaryDirectory() as d:
   a,_,_,_,_,_,_,c,approved=self.fixture(Path(d));approved['installedExeSha256']='unrelated'
   with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)
 def test_new_pair_cannot_change_raw_or_normalized_or_signature_evidence(self):
  for key in ('buildSha256','installedSha256','normalizedImageSha256','buildAuthenticode'):
   with self.subTest(key=key),tempfile.TemporaryDirectory() as d:
    a,_,_,_,_,fresh,path,c,approved=self.fixture(Path(d));fresh['pairs'][0][key]='forged';self.save(fresh,path,c)
    with self.assertRaisesRegex(ValueError,'lineage'):p.native_pin_inputs(approved,a,c)

if __name__=='__main__':unittest.main()
