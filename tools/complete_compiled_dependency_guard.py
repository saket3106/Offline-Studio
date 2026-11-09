from pathlib import Path
S=Path(__file__).resolve().parents[1];p=S/'in_place_packaging.py';s=p.read_text()
old="    output=recovery/'Offline GPT.exe'"
new="    for receipt in ['PACKAGING_COMPATIBILITY.json','COMPILED_SOURCE_ACCEPTANCE.json']:\n        if (root/'Documentation/VoiceRepair20261026'/receipt).exists():raise ValueError('Prior build evidence must be retained and reconciled: '+receipt)\n"+old
assert old in s;s=s.replace(old,new)
start=s.index('    for name,source,kind in analysis.pure:',s.index('def verify_compiled_application'))
end=s.index('    # Entry script lives',start)
s=s[:start]+'''    dependency_count=0
    for name,source,kind in analysis.pure:
        if name in pyz.toc:embedded=pyz.extract(name)
        elif name in archive.toc:embedded=marshal.loads(archive.extract(name))
        else:raise ValueError('Compiled module missing: '+name)
        if source in (None,'-'):
            if embedded is not None:raise ValueError('Compiled namespace differs: '+name)
            continue
        source=Path(source);fresh=load_module_code(source)
        if code_identity(embedded)!=code_identity(fresh):raise ValueError('Compiled dependency/source differs: '+name)
        if source.resolve().is_relative_to(canonical):checked.append(name)
        else:dependency_count+=1
    for name,source,kind in analysis.scripts:
        if code_identity(marshal.loads(archive.extract(name)))!=code_identity(load_module_code(source)):
            raise ValueError('Compiled executable script differs: '+name)
'''+s[end:]
s=s.replace("'compiledCanonicalModules':checked}","'compiledCanonicalModules':checked,'compiledDependencyModules':dependency_count,'compiledScripts':[r[0] for r in analysis.scripts]}")
compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
p=S/'tests/test_in_place_packaging.py';s=p.read_text();anchor="if __name__=='__main__':unittest.main()"
new=''' def test_poisoned_compiled_dependency_is_not_accepted_even_when_inputs_match(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   r=Path(folder);a=r/'Application';a.mkdir();s=r/'Source';s.mkdir();(a/'Offline GPT.exe').write_bytes(b'exe');analysis=self.analysis(r,[])
   vendor=r/'vendor.py';vendor.write_text('value=1');analysis.pure=[('vendor',str(vendor),'PYMODULE')];analysis.scripts=[]
   evidence={'status':'PASS','sourceManifestSha256':digest(s/'SOURCE_MANIFEST.sha256'),'canonicalSource':manifest_inputs(s),'entries':[],'pure':[{'module':'vendor','input':str(vendor),'inputSha256':digest(vendor)}],'scripts':[],'installedExeSha256':digest(a/'Offline GPT.exe')}
   receipt=r/'receipt.json';receipt.write_text(json.dumps(evidence))
   with patch('PyInstaller.archive.readers.CArchiveReader') as reader:
    pyz=reader.return_value.open_embedded_archive.return_value;pyz.toc={'vendor':(0,0,0)};pyz.extract.return_value=compile('value=999','vendor.py','exec')
    with self.assertRaisesRegex(ValueError,'Compiled dependency/source differs'):verify_compiled_application(r/'new.exe',analysis,s,receipt)

'''
assert anchor in s;s=s.replace(anchor,new+anchor);compile(s,str(p),'exec');p.write_text(s,encoding='utf-8')
print('Post-build checks now compare third-party compiled code and runtime scripts, not just input hashes.')
