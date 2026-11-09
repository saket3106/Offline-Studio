"""Read-only readiness audit; never invokes PyInstaller Analysis/build or models."""
from pathlib import Path
import ast,datetime,hashlib,json,marshal,sqlite3,sys,types,zipfile

def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def table_digests(connection):
    values={}
    for name, in connection.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        rows=connection.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()
        values[name]={'rows':len(rows),'sha256':hashlib.sha256(b''.join(sorted(hashlib.sha256(repr(row).encode()).digest() for row in rows))).hexdigest()}
    return values

def nested_codes(code,name):
    if isinstance(code,types.CodeType):
        if code.co_name==name:yield code
        for value in code.co_consts:yield from nested_codes(value,name)

def audit():
    from PyInstaller.archive.readers import CArchiveReader
    from in_place_packaging import code_identity
    source=Path(__file__).resolve().parent;root=source.parent;v=root/'Documentation/VoiceRepair20261026';r=root/'Recovery/VoiceRepair20261026';installation=root/'Application'
    baseline=json.loads((v/'BEFORE.json').read_text());checkpoint=json.loads((v/'FINAL_SOURCE_CHECKPOINT.json').read_text())
    expected=json.loads((v/'SOURCE_MANIFEST_AFTER.json').read_text());drift=[n for n,h in expected.items() if not (source/n).is_file() or sha(source/n)!=h]
    with sqlite3.connect((installation/'offline_gpt.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        db.execute('BEGIN');integrity=db.execute('PRAGMA quick_check').fetchall()==[('ok',)];current=table_digests(db)
        row=db.execute('SELECT * FROM operation_journal WHERE id=?',('56cf110e-9106-4cf9-b4c0-183c99e1281e',)).fetchone();db.rollback()
    with sqlite3.connect((r/'data-before.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
        oldrow=db.execute('SELECT * FROM operation_journal WHERE id=?',('56cf110e-9106-4cf9-b4c0-183c99e1281e',)).fetchone()
    archive=CArchiveReader(str(installation/'Offline GPT.exe'));installed_code=marshal.loads(archive.extract('app'))
    with zipfile.ZipFile(r/'source-before.zip') as z:oldcode=compile(z.read('app.py'),'prior-source/app.py','exec',dont_inherit=True,optimize=0)
    old_function=list(nested_codes(oldcode,'_speech_changed'));installed_function=list(nested_codes(installed_code,'_speech_changed'))
    matches=len(old_function)==len(installed_function)==1 and code_identity(old_function[0])==code_identity(installed_function[0])
    cfg=json.loads((installation/'offline_gpt_config.json').read_text());paths=[]
    tree=ast.parse((source/'integrated_runtime.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='resolve_path')
    for base in [source,installation]:
        env={'Path':Path,'APP_DIR':base};exec(compile(ast.Module([fn],[]),'resource-function','exec'),env)
        for name in ['gpt_oss_gguf','vision_model','vision_projector','voice_model_path','voice_server_path','sd_cli','flux_model','flux_encoder','flux_vae','flux_upscaler']:
            value=cfg.get(name,'');target=env['resolve_path'](value) if value else None
            paths.append({'mode':base.name,'key':name,'resolved':str(target) if target else None,'exists':bool(target and target.is_file())})
        for value in ['kokoro/model_quantized.onnx','kokoro/voices-v1.0.bin','ui/index.html','assistant_system_prompt.md']:
            target=env['resolve_path'](value);paths.append({'mode':base.name,'key':value,'resolved':str(target),'exists':target.is_file()})
    # Static inspection of the actual installed archive and retained inputs;
    # these observations do not substitute for an authorized actual Analysis.
    import PySide6,_sqlite3
    native=[('python312.dll',Path(sys.base_prefix)/'python312.dll'),('_sqlite3.pyd',Path(_sqlite3.__file__)),('sqlite3.dll',Path(sys.base_prefix)/'DLLs/sqlite3.dll')]
    q=Path(PySide6.__file__).parent
    for name in ['QtCore.pyd','QtGui.pyd','QtWidgets.pyd','QtWebEngineCore.pyd','QtWebEngineWidgets.pyd','QtWebChannel.pyd','QtMultimedia.pyd','Qt6Core.dll','Qt6Gui.dll','Qt6Widgets.dll','Qt6WebEngineCore.dll','Qt6WebEngineWidgets.dll','Qt6WebChannel.dll','Qt6Multimedia.dll']:
        native.append(('PySide6/'+name,q/name))
    native_rows=[{'name':name,'installed':str(installation/name),'input':str(p),'sameBytes':p.is_file() and (installation/name).is_file() and sha(p)==sha(installation/name),'installedSha256':sha(installation/name) if (installation/name).is_file() else None,'inputSha256':sha(p) if p.is_file() else None} for name,p in native]
    report={'scope':'Read-only checkpoint, production journal, resources and selected installed dependency audit; no Analysis/build/inference','checkpointManifestSha256':checkpoint['sourceManifestSha256'],'actualManifestSha256':sha(source/'SOURCE_MANIFEST.sha256'),'trackedSourceDrift':drift,'installedExeSha256':sha(installation/'Offline GPT.exe'),'installedExeMatchesCheckpoint':sha(installation/'Offline GPT.exe')==checkpoint['productionPreservation']['exeSha256'],'configMatchesBaseline':sha(installation/'offline_gpt_config.json')==baseline['configSha256'],'sqliteIntegrity':integrity,'productionTableCount':len(current),'changedTablesSinceBefore':[n for n in set(current)|set(baseline['tables']) if current.get(n)!=baseline['tables'].get(n)],'journalBefore':oldrow,'journalCurrent':row,'productionDataCorrectionPerformed':False,'oldInstalledSpeechFunctionMatchesPriorCanonicalSource':matches,'writerAttribution':'Not established; matching defect demonstrates capability, not which process wrote this row','journalDisposition':'Retain current row and both evidence snapshots. No authoritative replacement timestamp exists; recommend no production correction. Any correction requires separate explicit owner approval.','resourcePaths':paths,'selectedDependencyChecks':native_rows,'allSelectedDependenciesExact':all(x['sameBytes'] for x in native_rows),'actualPackagingClosure':'NOT_VERIFIED; spec not executed','builds':0,'installations':0}
    report_path=v/'READINESS_INITIAL.json'
    if report_path.exists():raise RuntimeError('Initial audit already exists; retain evidence and use a new reviewed receipt name')
    report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in {'resourcePaths','selectedDependencyChecks'}},indent=2))
    return report

def storage_inventory(root):
    """Allocated bytes inside one project only; never follow directory aliases."""
    import ctypes,os,time
    from ctypes import wintypes
    root=Path(root).resolve();kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    class StandardInfo(ctypes.Structure):
        _fields_=[('allocation',ctypes.c_longlong),('end',ctypes.c_longlong),('links',wintypes.DWORD),('deleted',ctypes.c_ubyte),('directory',ctypes.c_ubyte)]
    kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    kernel.CreateFileW.restype=wintypes.HANDLE
    kernel.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype=wintypes.BOOL
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    counts={};seen=set();errors=[];links=0;started=time.perf_counter()
    for directory,dirs,files in os.walk(root,followlinks=False):
        retained=[]
        for name in dirs:
            p=Path(directory)/name
            if p.is_symlink() or p.is_junction():links+=1
            else:retained.append(name)
        dirs[:]=retained
        for name in files:
            p=Path(directory)/name
            try:
                st=p.lstat()
                if st.st_file_attributes & 0x400:links+=1;continue
                identity=(st.st_dev,st.st_ino)
                if identity in seen:continue
                seen.add(identity)
                long_path=chr(92)*2+'?'+chr(92)+str(p)
                handle=kernel.CreateFileW(long_path,0x80,7,None,3,0x00200000,None)
                if handle==ctypes.c_void_p(-1).value:raise OSError(ctypes.get_last_error(),'attribute handle',str(p))
                try:
                    info=StandardInfo()
                    if not kernel.GetFileInformationByHandleEx(handle,1,ctypes.byref(info),ctypes.sizeof(info)):raise OSError(ctypes.get_last_error(),'allocation query',str(p))
                finally:kernel.CloseHandle(handle)
                row=counts.setdefault(p.relative_to(root).parts[0],{'files':0,'logicalBytes':0,'allocatedBytes':0})
                row['files']+=1;row['logicalBytes']+=st.st_size;row['allocatedBytes']+=info.allocation
            except OSError as exc:errors.append(str(exc))
    return {'method':'Win32 FileStandardInfo.AllocationSize; file attributes only','categories':counts,'allocatedBytes':sum(v['allocatedBytes'] for v in counts.values()),'logicalBytes':sum(v['logicalBytes'] for v in counts.values()),'errors':errors[:20],'errorCount':len(errors),'reparsePathsNotFollowed':links,'hardlinksCountedOnce':True,'seconds':time.perf_counter()-started}

if __name__=='__main__':
    raise SystemExit('Historical readiness audit is superseded by the installed v6 receipts. Import the bounded read-only helpers; do not rerun the old audit or deployment scripts.')
