"""Fresh independent signer observations must agree with every recorded identity."""
import copy,tempfile,unittest
from pathlib import Path
from in_place_packaging import digest,verify_native_signatures,installed_executable

class SignerObservationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
  build=self.root/'build.dll';installed=self.root/'installed.dll';build.write_bytes(b'fixture build');installed.write_bytes(b'fixture installed')
  self.pair={'buildInput':str(build),'buildSha256':digest(build),'installedInput':str(installed),'installedSha256':digest(installed),'buildAuthenticode':{'Status':'Valid','Subject':'Approved subject','Thumbprint':'build-cert'},'installedAuthenticode':{'Status':'Valid','Subject':'Approved subject','Thumbprint':'installed-cert'}}
  self.actual=[dict(self.pair[s],Path=self.pair[p]) for p,s in [('buildInput','buildAuthenticode'),('installedInput','installedAuthenticode')]]
 def test_exact_actual_certificates_pass(self):
  self.assertEqual(len(verify_native_signatures([self.pair],lambda paths:self.actual)),2)
 def test_valid_same_subject_different_certificate_is_rejected(self):
  actual=copy.deepcopy(self.actual);actual[0]['Thumbprint']='different-valid-certificate'
  with self.assertRaisesRegex(ValueError,'signer differs'):verify_native_signatures([self.pair],lambda paths:actual)
 def test_stale_installed_certificate_is_rejected(self):
  actual=copy.deepcopy(self.actual);actual[1]['Thumbprint']='actual-certificate'
  with self.assertRaisesRegex(ValueError,'signer differs'):verify_native_signatures([self.pair],lambda paths:actual)
 def test_invalid_status_and_changed_subject_are_rejected(self):
  for field,value in [('Status','NotTrusted'),('Subject','Other publisher')]:
   actual=copy.deepcopy(self.actual);actual[0][field]=value
   with self.subTest(field=field),self.assertRaisesRegex(ValueError,'signer differs'):verify_native_signatures([self.pair],lambda paths:actual)
 def test_missing_and_duplicate_observations_are_rejected(self):
  for actual in [self.actual[:1],self.actual+[self.actual[0]]]:
   with self.assertRaises(ValueError):verify_native_signatures([self.pair],lambda paths:actual)
 def test_hash_mismatch_is_rejected_before_signature_reader(self):
  Path(self.pair['buildInput']).write_bytes(b'changed')
  def unexpected(paths):raise AssertionError('Reader must not authorize changed bytes')
  with self.assertRaisesRegex(ValueError,'raw hash'):verify_native_signatures([self.pair],unexpected)
 def test_brand_migration_rejects_two_competing_executables(self):
  old=self.root/'Offline GPT.exe';old.touch();self.assertEqual(installed_executable(self.root),old)
  new=self.root/'Offline Studio.exe';new.touch()
  with self.assertRaisesRegex(ValueError,'exactly one'):installed_executable(self.root)
  old.unlink();self.assertEqual(installed_executable(self.root),new)

if __name__=='__main__':unittest.main()
