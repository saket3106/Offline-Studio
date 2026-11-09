"""The post-build gate must bind the actual single installed executable."""
import json,marshal,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from in_place_packaging import digest,verify_compiled_application

class IdentityTests(unittest.TestCase):
 def test_sdk_tls_policy_is_exact_required_and_canonical(self):
  from in_place_packaging import validate_analysis,SDK_TLS_POLICY_SHA256
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'Source';source.mkdir();app=root/'Application';app.mkdir();(app/'Offline Studio.exe').write_bytes(b'old');entry=source/'app.py';entry.write_text('pass\n');pem=source/'codex-rejected-cas.pem';pem.write_bytes((Path(__file__).parents[1]/pem.name).read_bytes());self.assertEqual(SDK_TLS_POLICY_SHA256,digest(pem))
   def seal():(source/'SOURCE_MANIFEST.sha256').write_text(digest(entry)+'  app.py\n'+digest(pem)+'  '+pem.name+'\n')
   seal();analysis=SimpleNamespace(binaries=[],datas=[(pem.name,str(pem),'DATA')],pure=[],scripts=[('app',str(entry),'PYSOURCE')])
   with patch('PyInstaller.archive.readers.CArchiveReader'):
    self.assertEqual('PASS',validate_analysis(analysis,app,source,root/'ok.json')['status'])
    other=root/'other.pem';other.write_bytes(pem.read_bytes());analysis.datas=[(pem.name,str(other),'DATA')]
    with self.assertRaisesRegex(ValueError,'swapped'):validate_analysis(analysis,app,source,root/'origin.json')
    analysis.datas=[]
    with self.assertRaisesRegex(ValueError,'Missing frontend'):validate_analysis(analysis,app,source,root/'missing.json')
    analysis.datas=[(pem.name,str(pem),'DATA')];pem.write_bytes(b'unapproved policy');seal()
    with self.assertRaisesRegex(ValueError,'distrust policy bytes changed'):validate_analysis(analysis,app,source,root/'bad.json')
 def test_branded_executable_is_verified_and_raw_drift_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'Source';source.mkdir();app=root/'Application';app.mkdir();installed=app/'Offline Studio.exe';installed.write_bytes(b'installed reviewed identity');entry=source/'app.py';entry.write_text('value=17\n');manifest=source/'SOURCE_MANIFEST.sha256';manifest.write_text(digest(entry)+'  app.py\n');candidate=root/'candidate.exe';candidate.write_bytes(b'candidate')
   evidence={'status':'PASS','sourceManifestSha256':digest(manifest),'canonicalSource':{'app.py':digest(entry)},'installedExeSha256':digest(installed),'entries':[],'pure':[],'scripts':[]};receipt=root/'receipt.json';receipt.write_text(json.dumps(evidence))
   class Archive:
    toc={'app':None}
    def open_embedded_archive(self,name):return SimpleNamespace(toc={})
    def extract(self,name):return marshal.dumps(compile(entry.read_bytes(),str(entry),'exec',dont_inherit=True,optimize=0))
   analysis=SimpleNamespace(pure=[],scripts=[])
   with patch('PyInstaller.archive.readers.CArchiveReader',return_value=Archive()):
    self.assertEqual(['app'],verify_compiled_application(candidate,analysis,source,receipt)['compiledCanonicalModules'])
    installed.write_bytes(b'swapped executable')
    with self.assertRaisesRegex(ValueError,'Installed EXE changed'):verify_compiled_application(candidate,analysis,source,receipt)
 def test_two_main_executables_remain_rejected(self):
  from in_place_packaging import installed_executable
  with tempfile.TemporaryDirectory() as folder:
   for name in ['Offline Studio.exe','Offline GPT.exe']:(Path(folder)/name).write_bytes(b'exe')
   with self.assertRaisesRegex(ValueError,'exactly one'):installed_executable(folder)
