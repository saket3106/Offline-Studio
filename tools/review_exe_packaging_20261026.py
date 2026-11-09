"""Apply the bounded packaging review; no PyInstaller execution or install."""
from pathlib import Path
import ast,hashlib,json,zipfile
S=Path(__file__).resolve().parents[1];F=S.parent;V=F/'Documentation/VoiceRepair20261026';R=F/'Recovery/VoiceRepair20261026'
before=json.loads((V/'SOURCE_MANIFEST_AFTER.json').read_text())
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
assert all(sha(S/n)==h for n,h in before.items()),'Reconcile source drift before editing'
archive=R/'packaging-review-before.zip'
with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
 for name in ['in_place_packaging.py','Offline GPT.inplace.spec','tests/test_in_place_packaging.py','docs/IN_PLACE_UPDATE.md','SOURCE_MANIFEST.sha256']:z.write(S/name,name)
with zipfile.ZipFile(archive) as z:assert all(hashlib.sha256(z.read(n)).hexdigest()==sha(S/n) for n in z.namelist())
p=S/'in_place_packaging.py';s=p.read_text()
s=s.replace("from pathlib import Path\n", "from pathlib import Path\nfrom runtime_contracts import windows_payload_path,validate_windows_payload_paths\n")
s=s.replace("return (code.co_argcount,", "return (code.co_name,code.co_qualname,code.co_argcount,")
anchor='def safe_destination(root,name):'
addition='''BUILD_ONLY_MODULES={'agent_packaging','in_place_packaging','packaging_readiness'}

def manifest_inputs(canonical):
    canonical=Path(canonical).resolve();entries={}
    for line in (canonical/'SOURCE_MANIFEST.sha256').read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'):continue
        checksum,name=line.split('  ',1)
        if len(checksum)!=64 or any(c not in '0123456789abcdef' for c in checksum):raise ValueError('Invalid source checksum')
        target=safe_destination(canonical,name)
        if name in entries or not target.is_file() or digest(target)!=checksum:raise ValueError('Source manifest mismatch: '+name)
        entries[name]=checksum
    validate_windows_payload_paths(list(entries))
    if 'app.py' not in entries:raise ValueError('Application entry missing from manifest')
    return entries

def runtime_modules(canonical,entries=None):
    entries=manifest_inputs(canonical) if entries is None else entries
    return {Path(n).stem:Path(canonical)/n for n in entries if '/' not in n and n.endswith('.py') and Path(n).stem not in BUILD_ONLY_MODULES|{'app'}}

def validate_build_locations(canonical,distpath,workpath,specname):
    """Pin actual PyInstaller globals, not only an example command line."""
    canonical=Path(canonical).absolute();root=canonical.parent
    if canonical.name!='Source' or specname!='Offline GPT.inplace':raise ValueError('Unexpected canonical spec identity')
    recovery=root/'Recovery/VoiceRepair20261026'
    expected_work=recovery/'Offline GPT.inplace'
    for supplied,expected in [(Path(distpath).absolute(),recovery),(Path(workpath).absolute(),expected_work)]:
        if supplied!=expected:raise ValueError('Build output/work path is not the approved transient location')
        for p in [supplied,*supplied.parents]:
            if p.is_symlink() or getattr(p,'is_junction',lambda:False)():raise ValueError('Redirected build path')
            if p==root:break
        if supplied.exists() and not supplied.is_dir():raise ValueError('Build directory is a file')
    output=recovery/'Offline GPT.exe'
    if output.exists():raise ValueError('Transient executable already exists; do not overwrite evidence')
    return {'distpath':str(recovery),'workpath':str(expected_work),'output':str(output)}

def load_module_code(path):
    path=Path(path)
    if path.suffix=='.py':return compile(path.read_bytes(),str(path),'exec',dont_inherit=True,optimize=0)
    if path.suffix=='.pyc':
        import importlib.util
        data=path.read_bytes()
        if data[:4]!=importlib.util.MAGIC_NUMBER:raise ValueError('Incompatible Python bytecode')
        return marshal.loads(data[16:])
    raise ValueError('Unsupported Python module input: '+str(path))

'''
assert anchor in s;s=s.replace(anchor,addition+anchor)
s=s.replace("    name=str(name).replace('\\\\','/')", "    name=windows_payload_path(str(name))")
s=s.replace("        aa={n for n in a.namelist() if n.endswith('.pyc')};bb={n for n in b.namelist() if n.endswith('.pyc')}", "        validate_windows_payload_paths(a.namelist());validate_windows_payload_paths(b.namelist())\n        if any(not n.endswith('.pyc') for n in a.namelist()+b.namelist()):raise ValueError('Unexpected frozen base-library member')\n        aa=set(a.namelist());bb=set(b.namelist())")
s=s.replace("    evidence={'status':'FAIL'", "    approved=manifest_inputs(canonical);required=runtime_modules(canonical,approved)\n    evidence={'sourceManifestSha256':digest(canonical/'SOURCE_MANIFEST.sha256'),'canonicalSource':approved,'status':'FAIL'")
s=s.replace("        destinations=set()", "        validate_windows_payload_paths([str(e[0]) for e in list(analysis.binaries)+list(analysis.datas)])\n        destinations=set()")
s=s.replace("row={'name':str(name),'inputSha256':digest(source),'kind':kind}", "row={'name':str(name),'input':str(source.resolve()),'inputSha256':digest(source),'kind':kind}")
start=s.index('        for name,source,kind in analysis.pure:');end=s.index("        evidence['status']='PASS'",start)
s=s[:start]+'''        observed={}
        for name,source,kind in analysis.pure:
            if name in observed:raise ValueError('Duplicate Python module: '+name)
            if source in (None,'-'):
                if name not in old.toc or old.extract(name) is not None:raise ValueError('Unverified namespace module: '+name)
                observed[name]=None;evidence['pure'].append({'module':name,'namespace':True});continue
            source=Path(source);app_source=source.resolve().is_relative_to(canonical)
            if name in required and source.resolve()!=required[name].resolve():raise ValueError('Shadowed canonical module: '+name)
            if app_source:
                if name not in required or source.resolve()!=required[name].resolve():raise ValueError('Unapproved canonical module: '+name)
            else:
                if name not in old.toc:raise ValueError('New unreviewed frozen dependency: '+name)
                if code_identity(old.extract(name))!=code_identity(load_module_code(source)):
                    raise ValueError('Frozen dependency source changed: '+name)
            observed[name]=str(source.resolve())
            evidence['pure'].append({'module':name,'input':str(source.resolve()),'inputSha256':digest(source),'canonical':app_source})
        missing=sorted(set(required)-set(observed))
        if missing:raise ValueError('Missing canonical modules: '+', '.join(missing))
'''+s[end:]
s=s.replace("def verify_compiled_application(exe,analysis,canonical):", "def verify_compiled_application(exe,analysis,canonical,compatibility_receipt):")
old="    canonical=Path(canonical).resolve();archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz');checked=[]"
new="""    canonical=Path(canonical).resolve()
    evidence=json.loads(Path(compatibility_receipt).read_text(encoding='utf-8'))
    if evidence.get('status')!='PASS' or evidence['sourceManifestSha256']!=digest(canonical/'SOURCE_MANIFEST.sha256') or evidence['canonicalSource']!=manifest_inputs(canonical):raise ValueError('Source changed during packaging')
    for row in evidence['entries']+evidence['pure']:
        if row.get('input') and digest(row['input'])!=row['inputSha256']:raise ValueError('Packaging input changed: '+row.get('module',row.get('name','unknown')))
    if digest(canonical.parent/'Application/Offline GPT.exe')!=evidence['installedExeSha256']:raise ValueError('Installed EXE changed during packaging')
    archive=CArchiveReader(str(exe));pyz=archive.open_embedded_archive('PYZ.pyz');checked=[]"""
assert old in s;s=s.replace(old,new)
s=s.replace("        source=Path(source)\n        if source.resolve().is_relative_to(canonical):", "        if source in (None,'-'):continue\n        source=Path(source)\n        if source.resolve().is_relative_to(canonical):")
ast.parse(s);p.write_text(s,encoding='utf-8')
p=S/'Offline GPT.inplace.spec';s=p.read_text();needle='from PyInstaller.utils.hooks import collect_all'
guard="""from pathlib import Path
import sys
canonical=Path(SPECPATH).absolute()
sys.path.insert(0,str(canonical))
from in_place_packaging import validate_build_locations,manifest_inputs,runtime_modules
validate_build_locations(canonical,DISTPATH,workpath,specnm)
approved_source=manifest_inputs(canonical)
required_modules=runtime_modules(canonical,approved_source)
"""
assert needle in s;s=s.replace(needle,guard+'\n'+needle,1)
s=s.replace("collect_agent_inputs('requirements-agent-windows-py312.lock')","collect_agent_inputs(canonical/'requirements-agent-windows-py312.lock')")
s=s.replace("    ['app.py'],\n    pathex=[],", "    [str(canonical/'app.py')],\n    pathex=[str(canonical)],")
s=s.replace("datas=[('ui', 'ui'), ('assistant_system_prompt.md', '.')]+voice_data+agent_data,", "datas=[(str(canonical/'ui'), 'ui'), (str(canonical/'assistant_system_prompt.md'), '.')]+voice_data+agent_data,")
s=s.replace("]+voice_imports+agent_imports,", "]+voice_imports+agent_imports+sorted(required_modules),")
s=s.replace("    icon='frontend-source/public/brand/offline-gpt.ico',", "    icon=str(canonical/'frontend-source/public/brand/offline-gpt.ico'),")
s=s.replace("receipt=canonical.parent/'Documentation/VoiceRepair20261026/COMPILED_SOURCE_ACCEPTANCE.json'\nreceipt.write_text(json.dumps(verify_compiled_application(exe.name,a,canonical),indent=2),encoding='utf-8')", "compiled_receipt=canonical.parent/'Documentation/VoiceRepair20261026/COMPILED_SOURCE_ACCEPTANCE.json'\ncompiled_receipt.write_text(json.dumps(verify_compiled_application(exe.name,a,canonical,receipt),indent=2),encoding='utf-8')")
ast.parse(s);assert 'COLLECT(' not in s;p.write_text(s,encoding='utf-8')
print(json.dumps({'rollback':str(archive),'rollbackSha256':sha(archive),'modified':['in_place_packaging.py','Offline GPT.inplace.spec'],'builds':0},indent=2))
