"""Reproduce the installed callback over in-memory SQLite, never production writes."""
from pathlib import Path
import ast,hashlib,json,marshal,sqlite3,sys,types
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S))
from packaging_readiness import sha,nested_codes,table_digests
from PyInstaller.archive.readers import CArchiveReader

def reproduce(code):
    db=sqlite3.connect(':memory:');db.execute('CREATE TABLE journal(id TEXT PRIMARY KEY,state TEXT,finished INTEGER)');clock=[0]
    def begin(ident,kind):db.execute('INSERT OR REPLACE INTO journal VALUES(?,?,NULL)',(ident,'running'))
    def finish(ident,state,error=None):
        clock[0]+=1;db.execute('UPDATE journal SET state=?,finished=? WHERE id=?',(state,clock[0],ident))
    bridge=types.SimpleNamespace(backend=types.SimpleNamespace(store=types.SimpleNamespace(workspace=types.SimpleNamespace(begin=begin,finish=finish)),voice_mode_active=False,busy=False),event=types.SimpleNamespace(emit=lambda _:None),speech_operation=None)
    callback=types.FunctionType(code,{'json':json})
    callback(bridge,{'operationId':'synthetic-speech','state':'loading'})
    callback(bridge,{'operationId':'synthetic-speech','state':'ready'})
    before=db.execute('SELECT state,finished FROM journal').fetchone()
    callback(bridge,{'operationId':'','state':'ready'})
    after=db.execute('SELECT state,finished FROM journal').fetchone();db.close()
    return {'afterReady':before,'afterStop':after,'terminalPreserved':before==after,'productionCalls':0}

F=S.parent;V=F/'Documentation/VoiceRepair20261026';A=F/'Application';checkpoint=json.loads((V/'FINAL_SOURCE_CHECKPOINT.json').read_text())
assert sha(A/'Offline GPT.exe')==checkpoint['productionPreservation']['exeSha256']
installed=marshal.loads(CArchiveReader(str(A/'Offline GPT.exe')).extract('app'));old=list(nested_codes(installed,'_speech_changed'));assert len(old)==1
tree=ast.parse((S/'app.py').read_text());node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_speech_changed');node.decorator_list=[]
new=list(nested_codes(compile(ast.Module([node],[]),'canonical-callback','exec'),'_speech_changed'));assert len(new)==1
old_test=reproduce(old[0]);new_test=reproduce(new[0]);assert old_test['afterStop'][0]=='cancelled' and new_test['terminalPreserved']
with sqlite3.connect((A/'offline_gpt.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    db.execute('BEGIN');digests=table_digests(db);row=db.execute('SELECT * FROM operation_journal WHERE id=?',('56cf110e-9106-4cf9-b4c0-183c99e1281e',)).fetchone();db.rollback()
result={'installedExeSha256':sha(A/'Offline GPT.exe'),'installedCallbackSyntheticReproduction':old_test,'repairedSourceCallbackSyntheticReproduction':new_test,'currentProductionRow':row,'disposition':'RECONCILED AS RETAINED HISTORICAL ANOMALY; NO DATA CORRECTION','writerAttribution':'Unknown. Installed bytecode demonstrably permits success-to-cancelled reclassification, but this is not proof of which process wrote the real row.','risk':'Historical operational status/timestamp remains unreliable for this one speech operation. No demonstrated chat, Library, document or model data loss. Do not fabricate a success or timestamp.','productionCorrectionAuthorized':False,'productionCorrectionPerformed':False,'correctionRequires':'Separate explicit owner approval and authoritative evidence for replacement values; no correction recommended now','productionTableDigests':digests,'inferenceCalls':0,'builds':0}
p=V/'JOURNAL_DISPOSITION.json';assert not p.exists();p.write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='productionTableDigests'},indent=2))
