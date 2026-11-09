from pathlib import Path
S=Path(__file__).resolve().parents[1]
p=S/'tests/test_in_place_packaging.py';s=p.read_text()
s=s.replace('from in_place_packaging import safe_destination,compare_base_zip,validate_analysis,code_identity','from in_place_packaging import safe_destination,compare_base_zip,validate_analysis,code_identity,digest,validate_build_locations,manifest_inputs,runtime_modules,verify_compiled_application')
s=s.replace("  return SimpleNamespace(binaries=entries,datas=[],pure=[])","  source=root/'Source';(source/'app.py').write_text('pass\\n')\n  (source/'SOURCE_MANIFEST.sha256').write_text(digest(source/'app.py')+'  app.py\\n')\n  return SimpleNamespace(binaries=entries,datas=[],pure=[])")
s=s.replace("self.assertRaisesRegex(ValueError,'Colliding')", "self.assertRaisesRegex(ValueError,'Duplicate Windows-equivalent')")
anchor="if __name__=='__main__':unittest.main()"
new=''' def test_actual_output_globals_reject_application_and_other_transient_paths(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'Source';source.mkdir();r=root/'Recovery/VoiceRepair20261026'
   self.assertEqual(validate_build_locations(source,r,r/'Offline GPT.inplace','Offline GPT.inplace')['output'],str(r/'Offline GPT.exe'))
   for dist,work in [(root/'Application',r/'Offline GPT.inplace'),(r,root/'Application'),(r/'other',r/'Offline GPT.inplace')]:
    with self.assertRaises(ValueError):validate_build_locations(source,dist,work,'Offline GPT.inplace')
   r.mkdir(parents=True);(r/'Offline GPT.exe').write_bytes(b'prior')
   with self.assertRaisesRegex(ValueError,'already exists'):validate_build_locations(source,r,r/'Offline GPT.inplace','Offline GPT.inplace')
 def test_missing_canonical_module_and_shadowing_are_independent_failures(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe')
   analysis=self.analysis(r,[]);module=s/'live_voice.py';module.write_text('value=1')
   (s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\\n'+digest(module)+'  live_voice.py\\n')
   with patch('PyInstaller.archive.readers.CArchiveReader'):
    with self.assertRaisesRegex(ValueError,'Missing canonical modules'):validate_analysis(analysis,a,s,r/'missing.json')
    shadow=r/'live_voice.py';shadow.write_text('value=1');analysis.pure=[('live_voice',str(shadow),'PYMODULE')]
    with self.assertRaisesRegex(ValueError,'Shadowed'):validate_analysis(analysis,a,s,r/'shadow.json')
 def test_manifest_drift_and_duplicate_names_fail_before_packaging(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'Source';source.mkdir();self.analysis(root,[])
   self.assertIn('app.py',manifest_inputs(source));(source/'app.py').write_text('changed')
   with self.assertRaisesRegex(ValueError,'manifest mismatch'):manifest_inputs(source)
 def test_namespace_inputs_are_verified_without_inventing_a_source_file(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[]);analysis.pure=[('vendor',None,'PYMODULE')]
   old=Mock();old.toc={'vendor':(3,0,0)};old.extract.return_value=None
   with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
    reader.return_value.open_embedded_archive.return_value=old
    self.assertEqual(validate_analysis(analysis,a,s,r/'namespace.json')['status'],'PASS')
    old.extract.return_value=compile('x=1','vendor.py','exec')
    with self.assertRaisesRegex(ValueError,'namespace'):validate_analysis(analysis,a,s,r/'bad.json')
 def test_source_drift_after_compatibility_never_reaches_compiled_acceptance(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[])
   evidence={'status':'PASS','sourceManifestSha256':digest(s/'SOURCE_MANIFEST.sha256'),'canonicalSource':manifest_inputs(s),'entries':[],'pure':[],'installedExeSha256':digest(a/'Offline GPT.exe')}
   receipt=r/'receipt.json';receipt.write_text(json.dumps(evidence));(s/'app.py').write_text('x=2');(s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\\n')
   with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
    with self.assertRaisesRegex(ValueError,'Source changed'):verify_compiled_application(r/'new.exe',analysis,s,receipt)
    reader.assert_not_called()
 def test_build_only_helpers_are_not_required_in_the_application_archive(self):
  entries={n:'0'*64 for n in ['app.py','live_voice.py','voice_runtime.py','in_place_packaging.py','packaging_readiness.py','agent_packaging.py']}
  self.assertEqual(set(runtime_modules(Path('Source'),entries)),{'live_voice','voice_runtime'})
 def test_spec_rejects_unapproved_execution_before_analysis(self):
  import os
  spec=(Path(__file__).resolve().parents[1]/'Offline GPT.inplace.spec').read_text()
  sentinel=Mock(side_effect=AssertionError('Analysis must not run'))
  with patch.dict(os.environ,{},clear=False):
   os.environ.pop('OFFLINEGPT_APPROVED_INPLACE_BUILD',None)
   with self.assertRaisesRegex(RuntimeError,'Fresh owner approval'):exec(compile(spec,'isolated-spec-test','exec'),{'Analysis':sentinel})
  sentinel.assert_not_called()

'''
assert anchor in s;s=s.replace(anchor,new+anchor);s=s.replace('from unittest.mock import patch','from unittest.mock import patch,Mock');compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Expanded targeted packaging guard coverage. No build invocation.')
