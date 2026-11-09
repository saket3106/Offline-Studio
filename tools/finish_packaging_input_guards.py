from pathlib import Path
S=Path(__file__).resolve().parents[1];p=S/'in_place_packaging.py';s=p.read_text()
s=s.replace("    expected_work=recovery/'Offline GPT.inplace'", "    expected_work=recovery/'Offline GPT.inplace'\n    if canonical.is_symlink() or getattr(canonical,'is_junction',lambda:False)():raise ValueError('Redirected canonical source')")
s=s.replace("        if supplied.exists() and not supplied.is_dir():raise ValueError('Build directory is a file')", "        if supplied.exists() and not supplied.is_dir():raise ValueError('Build directory is a file')\n    if expected_work.exists() and any(expected_work.iterdir()):raise ValueError('Stale build work must be reviewed before this one build')\n    cache=recovery/'Offline GPT.inplace-import-cache'\n    if cache.exists():raise ValueError('Import cache must be fresh, not reused')")
s=s.replace("'entries':[],'pure':[],'errors':[]}","'entries':[],'pure':[],'scripts':[],'errors':[]}")
s=s.replace("        destinations=set()", "        required_assets={n.casefold():n for n in approved if n.startswith('ui/') or n=='assistant_system_prompt.md'}\n        destinations=set()")
s=s.replace("row={'name':str(name),'input':str(source.resolve()),'inputSha256':digest(source),'kind':kind}", "row={'name':str(name),'input':str(source.resolve()),'inputSha256':digest(source),'installedSha256':digest(target) if target.is_file() else None,'kind':kind}")
old="""            elif changed_ui or key=='assistant_system_prompt.md':
                if not source.resolve().is_relative_to(canonical):raise ValueError('Noncanonical application asset')
                row['applicationAsset']=True"""
new="""            elif changed_ui or key=='assistant_system_prompt.md':
                if key not in required_assets or source.resolve()!=(canonical/required_assets[key]).resolve() or row['inputSha256']!=approved[required_assets[key]]:raise ValueError('Noncanonical or swapped application asset: '+str(name))
                row['applicationAsset']=True"""
assert old in s;s=s.replace(old,new)
s=s.replace("        observed={}", "        missing_assets=sorted(set(required_assets)-destinations)\n        if missing_assets:raise ValueError('Missing frontend/application assets: '+', '.join(missing_assets))\n        script_names=set()\n        for name,source,kind in analysis.scripts:\n            if name in script_names:raise ValueError('Duplicate executable script: '+name)\n            script_names.add(name);source=Path(source)\n            if name=='app':\n                if source.resolve()!=(canonical/'app.py').resolve():raise ValueError('Shadowed application entry')\n            elif name not in old_archive.toc or code_identity(marshal.loads(old_archive.extract(name)))!=code_identity(load_module_code(source)):\n                raise ValueError('Unreviewed executable runtime hook: '+name)\n            evidence['scripts'].append({'module':name,'input':str(source.resolve()),'inputSha256':digest(source)})\n        if 'app' not in script_names:raise ValueError('Application entry script missing')\n        observed={}")
s=s.replace("        old=CArchiveReader(str(installation/'Offline GPT.exe')).open_embedded_archive('PYZ.pyz')", "        old_archive=CArchiveReader(str(installation/'Offline GPT.exe'));old=old_archive.open_embedded_archive('PYZ.pyz')")
s=s.replace("            if source in (None,'-'):\n                if name not in old.toc", "            if source in (None,'-'):\n                if name in required:raise ValueError('Canonical module cannot be a namespace: '+name)\n                if name not in old.toc")
s=s.replace("    for row in evidence['entries']+evidence['pure']:", "    for row in evidence['entries']+evidence['pure']+evidence['scripts']:")
old="    if digest(canonical.parent/'Application/Offline GPT.exe')!=evidence['installedExeSha256']:raise ValueError('Installed EXE changed during packaging')"
new="""    for row in evidence['entries']:
        target=safe_destination(canonical.parent/'Application',row['name'])
        if (digest(target) if target.is_file() else None)!=row['installedSha256']:raise ValueError('Installed dependency/asset changed during packaging: '+row['name'])
"""+old
assert old in s;s=s.replace(old,new)
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=S/'tests/test_in_place_packaging.py';s=p.read_text()
old="  source=root/'Source';(source/'app.py').write_text('pass\\n')\n  (source/'SOURCE_MANIFEST.sha256').write_text(digest(source/'app.py')+'  app.py\\n')\n  return SimpleNamespace(binaries=entries,datas=[],pure=[])"
new="  source=root/'Source';(source/'app.py').write_text('pass\\n')\n  (source/'SOURCE_MANIFEST.sha256').write_text(digest(source/'app.py')+'  app.py\\n')\n  return SimpleNamespace(binaries=entries,datas=[],pure=[],scripts=[('app',str(source/'app.py'),'PYSOURCE')])"
assert old in s;s=s.replace(old,new)
old="'entries':[],'pure':[],'installedExeSha256'";s=s.replace(old,"'entries':[],'pure':[],'scripts':[],'installedExeSha256'")
anchor="if __name__=='__main__':unittest.main()"
new=''' def test_missing_or_swapped_frontend_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[])
   ui=s/'ui';ui.mkdir();index=ui/'index.html';index.write_text('current');other=ui/'other.html';other.write_text('wrong')
   (s/'SOURCE_MANIFEST.sha256').write_text(digest(s/'app.py')+'  app.py\\n'+digest(index)+'  ui/index.html\\n'+digest(other)+'  ui/other.html\\n')
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

'''
assert anchor in s;s=s.replace(anchor,new+anchor);compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Required assets, executable hook closure, source/installed input drift and stale-cache guards completed.')
