"""Compatibility gates only. No PyInstaller analysis/build or application writes."""
import ast,marshal,tempfile,unittest,zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from in_place_packaging import safe_destination,compare_base_zip,validate_analysis,code_identity,digest,validate_build_locations,manifest_inputs,runtime_modules,verify_compiled_application

class PackagingTests(unittest.TestCase):
 def test_exe_only_spec_has_no_collector_and_checks_before_exe(self):
  p=Path(__file__).resolve().parents[1]/'Offline GPT.inplace.spec';tree=ast.parse(p.read_text())
  calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
  self.assertFalse(any(isinstance(n.func,ast.Name) and n.func.id=='COLLECT' for n in calls))
  exe=next(n for n in calls if isinstance(n.func,ast.Name) and n.func.id=='EXE')
  gate=next(n for n in calls if isinstance(n.func,ast.Name) and n.func.id=='validate_analysis')
  self.assertLess(gate.lineno,exe.lineno)
  options={k.arg:ast.literal_eval(k.value) for k in exe.keywords if k.arg in {'exclude_binaries','console'}}
  icon=next(k.value for k in exe.keywords if k.arg=='icon');self.assertIn('canonical',ast.unparse(icon))
  self.assertTrue(options['exclude_binaries']);self.assertFalse(options['console'])
 def test_destination_rejects_traversal_absolute_and_alternate_streams(self):
  with tempfile.TemporaryDirectory() as folder:
   for name in ['../private.db','x/../../data','C:/outside.dll','/outside','x:stream','x//y','x/./y']:
    with self.assertRaises(ValueError):safe_destination(folder,name)
   self.assertEqual(safe_destination(folder,'PySide6/QtCore.pyd'),Path(folder).resolve()/'PySide6/QtCore.pyd')
 def test_base_library_ignores_only_code_metadata_not_instructions(self):
  with tempfile.TemporaryDirectory() as folder:
   def make(name,text,filename):
    p=Path(folder)/name
    with zipfile.ZipFile(p,'w') as z:z.writestr('module.pyc',__import__('importlib.util').util.MAGIC_NUMBER+b'\0'*12+marshal.dumps(compile(text,filename,'exec')))
    return p
   a=make('a.zip','value=3','old-build/module.py');b=make('b.zip','value=3','new-build/module.py');c=make('c.zip','value=4','new-build/module.py')
   self.assertEqual(compare_base_zip(a,b),1)
   with self.assertRaisesRegex(ValueError,'Incompatible'):compare_base_zip(a,c)
 def analysis(self,root,entries):
  source=root/'Source';(source/'app.py').write_text('pass\n')
  (source/'SOURCE_MANIFEST.sha256').write_text(digest(source/'app.py')+'  app.py\n')
  return SimpleNamespace(binaries=entries,datas=[],pure=[],scripts=[('app',str(source/'app.py'),'PYSOURCE')])
 def test_changed_external_dependency_fails_without_copying(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe')
   (a/'runtime.dll').write_bytes(b'old');fresh=r/'runtime.dll';fresh.write_bytes(b'new');receipt=r/'receipt.json'
   with patch('PyInstaller.archive.readers.CArchiveReader'):
    with self.assertRaisesRegex(ValueError,'absent or different'):validate_analysis(self.analysis(r,[('runtime.dll',str(fresh),'BINARY')]),a,s,receipt)
   self.assertEqual((a/'runtime.dll').read_bytes(),b'old');self.assertIn('FAIL',receipt.read_text())
 def test_same_dependency_passes_but_case_collision_fails(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');dll=a/'runtime.dll';dll.write_bytes(b'fixed')
   one=('runtime.dll',str(dll),'BINARY')
   with patch('PyInstaller.archive.readers.CArchiveReader'):
    self.assertEqual(validate_analysis(self.analysis(r,[one]),a,s,r/'ok.json')['status'],'PASS')
    with self.assertRaisesRegex(ValueError,'Duplicate Windows-equivalent'):validate_analysis(self.analysis(r,[one,('RUNTIME.DLL',str(dll),'BINARY')]),a,s,r/'fail.json')

 def test_actual_output_globals_reject_application_and_other_transient_paths(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);source=root/'Source';source.mkdir();r=root/'Recovery/VoiceRepair20261026'
   self.assertEqual(validate_build_locations(source,r,r/'Offline GPT.inplace','Offline GPT.inplace')['output'],str(r/'Offline GPT.inplace/Offline Studio.exe'))
   for dist,work in [(root/'Application',r/'Offline GPT.inplace'),(r,root/'Application'),(r/'other',r/'Offline GPT.inplace')]:
    with self.assertRaises(ValueError):validate_build_locations(source,dist,work,'Offline GPT.inplace')
   r.mkdir(parents=True);(r/'Offline GPT.exe').write_bytes(b'prior')
   with self.assertRaisesRegex(ValueError,'already exists'):validate_build_locations(source,r,r/'Offline GPT.inplace','Offline GPT.inplace')
 def test_missing_canonical_module_and_shadowing_are_independent_failures(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe')
   analysis=self.analysis(r,[]);module=s/'live_voice.py';module.write_text('value=1')
   (s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\n'+digest(module)+'  live_voice.py\n')
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
   evidence={'status':'PASS','sourceManifestSha256':digest(s/'SOURCE_MANIFEST.sha256'),'canonicalSource':manifest_inputs(s),'entries':[],'pure':[],'scripts':[],'installedExeSha256':digest(a/'Offline GPT.exe')}
   receipt=r/'receipt.json';receipt.write_text(json.dumps(evidence));(s/'app.py').write_text('x=2');(s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\n')
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

 def test_missing_or_swapped_frontend_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[])
   ui=s/'ui';ui.mkdir();index=ui/'index.html';index.write_text('current');other=ui/'other.html';other.write_text('wrong')
   (s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\n'+digest(index)+'  ui/index.html\n'+digest(other)+'  ui/other.html\n')
   with patch('PyInstaller.archive.readers.CArchiveReader'):
    with self.assertRaisesRegex(ValueError,'Missing frontend'):validate_analysis(analysis,a,s,r/'missing-ui.json')
    analysis.datas=[('ui/index.html',str(other),'DATA'),('ui/other.html',str(index),'DATA')]
    with self.assertRaisesRegex(ValueError,'swapped'):validate_analysis(analysis,a,s,r/'swapped-ui.json')
 def test_missing_entry_or_new_runtime_hook_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[]);analysis.scripts=[]
   with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
    with self.assertRaisesRegex(ValueError,'entry script missing'):validate_analysis(analysis,a,s,r/'missing-entry.json')
    hook=r/'hook.py';hook.write_text('x=1');analysis.scripts=[('app',str(s/'app.py'),'PYSOURCE'),('new_hook',str(hook),'PYSOURCE')];reader.return_value.toc={}
    with self.assertRaisesRegex(ValueError,'Unreviewed executable'):validate_analysis(analysis,a,s,r/'hook.json')
 def test_stale_work_and_import_cache_cannot_be_reused(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);s=r/'Source';s.mkdir();out=r/'Recovery/VoiceRepair20261026';work=out/'Offline GPT.inplace';work.mkdir(parents=True);(work/'injected.pyc').write_bytes(b'poison')
   with self.assertRaisesRegex(ValueError,'Stale build work'):validate_build_locations(s,out,work,'Offline GPT.inplace')

 def test_poisoned_compiled_dependency_is_not_accepted_even_when_inputs_match(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[])
   vendor=r/'vendor.py';vendor.write_text('value=1');analysis.pure=[('vendor',str(vendor),'PYMODULE')];analysis.scripts=[]
   evidence={'status':'PASS','sourceManifestSha256':digest(s/'SOURCE_MANIFEST.sha256'),'canonicalSource':manifest_inputs(s),'entries':[],'pure':[{'module':'vendor','input':str(vendor),'inputSha256':digest(vendor)}],'scripts':[],'installedExeSha256':digest(a/'Offline GPT.exe')}
   receipt=r/'receipt.json';receipt.write_text(json.dumps(evidence))
   with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
    pyz=reader.return_value.open_embedded_archive.return_value;pyz.toc={'vendor':(0,0,0)};pyz.extract.return_value=compile('value=999','vendor.py','exec')
    with self.assertRaisesRegex(ValueError,'Compiled dependency/source differs'):verify_compiled_application(r/'new.exe',analysis,s,receipt)

if __name__=='__main__':unittest.main()
