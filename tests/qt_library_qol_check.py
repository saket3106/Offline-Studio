"""Actual candidate EXE, synthetic isolated Library/chat data, no inference.

Native permanent-delete confirmations remain real. --native waits for manual
controller confirmation while the UI is inspected; never auto-accepts Qt dialogs.
"""
import base64,hashlib,json,os,sqlite3,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
LOG=Path(os.environ.get('OFFLINE_GPT_CHECK_LOG',ROOT/'logs/library-qol-20261015'))
LOG.mkdir(exist_ok=True)
PROFILE=Path(os.environ.get('OFFLINE_GPT_TEST_PROFILE',LOG/'packaged-profile'))
PKG=ROOT/'logs/comprehensive-sprint/candidate/Offline GPT'
transport=(ROOT/'tests/qt_sprint_check.py').read_text(encoding='utf-8').split('import sqlite3,uuid')[0]
transport=transport.replace("        if value.get('method')=='Page.javascriptDialogOpening':\n            ws.sendTextMessage(json.dumps({'id':999999,'method':'Page.handleJavaScriptDialog','params':{'accept':True}}))",'        # Never automatically accept a dialog in destructive-operation tests.')
exec(transport)
from PIL import Image
from PySide6.QtNetwork import QAbstractSocket
port=9249
env.update(OFFLINE_GPT_DATA_DIR=str(PROFILE),QTWEBENGINE_REMOTE_DEBUGGING=f'127.0.0.1:{port}',QTWEBENGINE_CHROMIUM_FLAGS=env['QTWEBENGINE_CHROMIUM_FLAGS']+' --disable-gpu --disable-background-timer-throttling --disable-renderer-backgrounding')
PROFILE=PROFILE.resolve();LOG=LOG.resolve()
if not LOG.is_relative_to(ROOT/'logs') or not PROFILE.is_relative_to(LOG):raise RuntimeError('Use an isolated profile inside this test log directory.')
PROFILE.mkdir(exist_ok=True)
marker=PROFILE/'synthetic-library-qol.marker'
if '--restart' in sys.argv and (not marker.exists() or marker.read_text()!='synthetic fixtures only'):raise RuntimeError('Restart only a profile created by this synthetic test.')
if '--restart' not in sys.argv:
    assert not (PROFILE/'offline_gpt.sqlite3').exists(),'Use a fresh isolated profile'
    marker.write_text('synthetic fixtures only')
    cfg=json.loads((ROOT.parent/'Offline GPT/offline_gpt_config.json').read_text())
    cfg.update(backup_schedule_enabled=False,image_output_directory=str(PROFILE/'generated'),chat_backend='bundled')
    (PROFILE/'offline_gpt_config.json').write_text(json.dumps(cfg))
    (PROFILE/'generated').mkdir()
    for name,color in [('parent',(35,35,35)),('child',(180,20,20)),('unrelated',(20,150,80)),('delete-me',(40,80,120))]:
        Image.new('RGB',(128,72),color).save(PROFILE/'generated'/f'{name}.png')
report={'checks':{},'exeSha256':hashlib.sha256((PKG/'Offline GPT.exe').read_bytes()).hexdigest(),'started':time.time(),'profile':str(PROFILE),'realInference':False}
def close_normally():
    if process.poll() is None:
        try:js("window.offlineNative?.closeApp()")
        except Exception:pass
        for _ in range(200):
            if process.poll() is not None:return True
            wait(100)
    return process.poll() is not None

def native_request(expr,phase):
    marker=LOG/(phase+'-native.done')
    if marker.exists():raise RuntimeError('Preserve native evidence; choose a fresh log directory.')
    # Native Qt modality can delay CDP replies. Send without waiting, then let
    # the external controller observe/click the real dialog and acknowledge it.
    ws.sendTextMessage(json.dumps({'id':880000 if phase=='cancel' else 880001,'method':'Runtime.evaluate','params':{'expression':expr,'returnByValue':True}}))
    (LOG/'native-phase.txt').write_text(phase)
    print('NATIVE_CONFIRMATION_READY: '+phase,flush=True)
    for _ in range(1800):
        if marker.exists():return js('window.qolPermanentResult')
        wait(100)
    raise TimeoutError('Native confirmation '+phase)

def save():
    report['seconds']=round(time.time()-report['started'],3)
    report['javascriptDialogs']=[event for event in events if event.get('method')=='Page.javascriptDialogOpening']
    (LOG/('packaged-restart.json' if '--restart' in sys.argv else 'packaged-library-qol.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
def check(name,value):
    report['checks'][name]=bool(value);save();print(('PASS ' if value else 'FAIL ')+name,flush=True)
def api(name,*args):
    result=command('Runtime.evaluate',{'expression':'new Promise(resolve=>window.offlineNative['+json.dumps(name)+']('+','.join(json.dumps(a) for a in args)+(',resolve' if args else 'resolve')+'))','returnByValue':True,'awaitPromise':True},30)
    if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
    raw=result.get('result',{}).get('value')
    try:return json.loads(raw)
    except (ValueError,TypeError):return raw
def task(action,args):
    r=api('workspaceRequest',action,json.dumps(args))
    if not r.get('ok'):raise RuntimeError(str(r))
    for _ in range(600):
        result=js('window.qolResults['+json.dumps(r['requestId'])+']')
        if result:
            if not result.get('ok'):raise RuntimeError(str(result))
            return result['value']
        wait(50)
    raise TimeoutError(action)
def button(text):
    js('[...document.querySelectorAll("button")].find(e=>e.textContent.trim()==='+json.dumps(text)+').click()');wait(180)
def field(selector,value):
    js('(()=>{const e=document.querySelector('+json.dumps(selector)+');Object.getOwnPropertyDescriptor(e.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,"value").set.call(e,'+json.dumps(value)+');e.dispatchEvent(new Event("input",{bubbles:true}));})()');wait(300)
def view(mode):
    selector=json.dumps('[aria-label="Library visibility"]')
    js('(()=>{let e=document.querySelector('+selector+');e.value='+json.dumps(mode)+';e.dispatchEvent(new Event("change",{bubbles:true}));})()');wait(300)
def db():return sqlite3.connect(PROFILE/'offline_gpt.sqlite3')
process=subprocess.Popen([str(PKG/'Offline GPT.exe')],cwd=PKG,env=env,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
try:
    targets=[]
    for _ in range(200):
        if process.poll() is not None:raise RuntimeError('Candidate exited')
        try:
            targets=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1).read())
            if targets:break
        except Exception:pass
        wait(100)
    ws.open(QUrl(next(t for t in targets if t.get('type')=='page')['webSocketDebuggerUrl']))
    for _ in range(100):
        if ws.state()==QAbstractSocket.SocketState.ConnectedState:break
        wait(100)
    command('Page.enable');wait(900)
    check('real_packaged_bridge',js("(()=>{const root=document.querySelector('#root');const f=root[Object.keys(root).find(k=>k.startsWith('__reactContainer$'))];const seen=new Set();function find(n){if(!n||seen.has(n))return null;seen.add(n);for(let h=n.memoizedState;h;h=h.next){if(h.memoizedState?.workspaceRequest)return h.memoizedState;}return find(n.child)||find(n.sibling)||find(n.alternate);}window.offlineNative=find(f);window.qolResults={};window.offlineNative.event.connect(raw=>{const e=JSON.parse(raw);if(e.type==='workspaceResult')window.qolResults[e.requestId]=e;});return !!window.offlineNative;})()"))
    if '--restart' in sys.argv:
        with db() as c:
            check('restart_purge_tombstone_persists',c.execute("SELECT deleted FROM library_images WHERE path LIKE '%delete-me.png'").fetchone()[0]==2)
            check('restart_version_link_persists',c.execute("SELECT count(*) FROM image_versions WHERE operation='recolor'").fetchone()[0]==1)
            check('restart_draft_saved',bool(c.execute("SELECT value FROM intelligence_meta WHERE key LIKE 'draft:%' AND value LIKE '%Final close draft%'").fetchone()))
            check('restart_database_integrity',c.execute('PRAGMA integrity_check').fetchone()[0]=='ok')
        # Preserve missing parent identity in a real comparison, then restore the
        # synthetic source immediately. No production filesystem paths involved.
        with db() as c:
            parent_id=c.execute("SELECT id FROM library_images WHERE path LIKE '%parent.png'").fetchone()[0]
            child_id=c.execute("SELECT id FROM library_images WHERE path LIKE '%child.png'").fetchone()[0]
        parent=PROFILE/'generated/parent.png';held=PROFILE/'generated/parent-review-held.png'
        if held.exists() or not parent.resolve().is_relative_to(PROFILE/'generated'):raise RuntimeError('Unsafe synthetic move target.')
        parent.rename(held)
        try:
            family=api('getLibraryVersions',child_id)['images'];missing=next(i for i in family if i['id']==parent_id)
            check('restart_missing_parent_explicitly_preserved',missing['fileExists'] is False and missing['displayName']=='Original file missing')
        finally:held.rename(parent)
        button('Library');wait(250)
        field('.library-search-input','My black car')
        js("document.querySelector('.library-menu-trigger').click()");wait(80)
        js("[...document.querySelectorAll('[role=menuitem]')].find(e=>e.textContent==='Compare Versions').click()");wait(200)
        check('actual_version_comparison_loaded',js("document.querySelectorAll('.library-compare-dialog .image-compare figure').length===2&&[...document.querySelectorAll('.library-compare-dialog .image-compare img')].every(e=>e.complete&&e.naturalWidth>0)"))
        check('comparison_shows_basename_without_private_path',js("document.querySelector('[aria-label=\"after version\"] option:checked').textContent.trim()==='child.png'"))
        (LOG/'version-comparison.png').write_bytes(base64.b64decode(command('Page.captureScreenshot',{'format':'png'})['data']))
        button('Close comparison');field('.library-search-input','')
        view('hidden')
        check('restart_recovery_review_visible',js("[...document.querySelectorAll('button')].some(e=>e.textContent.includes('Recovery (1)'))"))
        button('Recovery (1)')
        check('restart_unknown_not_claimed_success',js("document.querySelector('.library-recovery').textContent.includes('Outcome: unknown')"))
    else:
        items=api('getLibraryImages');ids={Path(i['path']).stem:i['id'] for i in items};report['imageIds']=ids;save()
        assert set(ids)=={'parent','child','unrelated','delete-me'},ids
        with db() as c:
            c.execute('UPDATE library_images SET user_prompt=?,model=?,final_dimensions=?,file_size=? WHERE id=?',('Original black car','Fixture model','128 × 72',900,ids['parent']))
            c.execute("INSERT INTO image_versions VALUES(?,?,?,?)",(ids['child'],ids['parent'],'recolor',json.dumps({'durationSeconds':.05,'color':'red'})))
        original={name:hashlib.sha256((PROFILE/'generated'/f'{name}.png').read_bytes()).hexdigest() for name in ids}
        unrelated_row=None
        with db() as c:unrelated_row=c.execute('SELECT * FROM library_images WHERE id=?',(ids['unrelated'],)).fetchone()
        button('Library');wait(300)
        check('library_displays_four_real_files',js("document.querySelectorAll('.library-card').length===4"))
        js("document.querySelector('.library-menu-trigger').click()");wait(80)
        check('real_context_menu_actions',js("['Open','Edit','Rename','Download','Show Details','Delete'].every(t=>[...document.querySelectorAll('[role=menuitem]')].some(e=>e.textContent===t))"))
        js("document.querySelector('[role=menu]').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");wait(60)
        js("document.querySelector('.library-card').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,clientX:420,clientY:250}))");wait(60)
        check('real_right_click_menu',js("!!document.querySelector('[role=menu]')"))
        js("document.querySelector('[role=menu]').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        rename=task('libraryRename',{'id':ids['parent'],'name':'My black car'})
        check('real_rename_metadata_only',rename['physicalFilesChanged'] is False and (PROFILE/'generated/parent.png').exists())
        api('refreshLibrary',False);button('Refresh');field('.library-search-input','Fixture model')
        check('real_metadata_search',js("document.querySelectorAll('.library-card').length===1&&document.querySelector('.library-card').textContent.includes('My black car')"))
        field('.library-search-input','')
        check('real_sort_controls',js("!!document.querySelector('option[value=name]')&&!!document.querySelector('option[value=size]')"))
        family=api('getLibraryVersions',ids['child']);check('real_family_relationship',set(i['id'] for i in family['images'])=={ids['parent'],ids['child']})
        result=task('libraryManage',{'ids':[ids['parent'],ids['child']],'action':'hide'})
        check('bulk_trash_two',result['completed']==2)
        check('trash_preserves_original_hashes',all(hashlib.sha256((PROFILE/'generated'/f'{name}.png').read_bytes()).hexdigest()==digest for name,digest in original.items()))
        view('hidden');check('trash_ui_two',js("document.querySelectorAll('.library-card').length===2"))
        result=task('libraryManage',{'ids':[ids['parent'],ids['child']],'action':'restore'})
        check('bulk_restore_two',result['completed']==2)
        check('restore_version_relationship',len(api('getLibraryVersions',ids['child'])['images'])==2)
        export=task('libraryExport',{'ids':[ids['parent'],ids['child']],'path':str(PROFILE/'images.zip')})
        with zipfile.ZipFile(export['path']) as z:
            meta=json.loads(z.read('manifest.json'));check('real_export_original_bytes',hashlib.sha256(z.read(meta['images'][0]['archiveName'])).hexdigest()==original['parent'])
            check('real_export_name_and_version_metadata',meta['images'][0]['displayName']=='My black car' and meta['images'][1]['version']['parentId']==ids['parent'])
        cid=api('newChat');check('draft_bridge_save',api('savePromptDraft',cid,json.dumps({'text':'Persistent draft','attachments':[]}))['ok'])
        other=api('newChat');api('loadChat',cid)
        check('draft_bridge_restore',api('getPromptDraft',cid)['text']=='Persistent draft')
        with db() as c:
            cur=c.execute("INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)",(cid,'assistant','Saved distinctive response LANTERN',time.time(),'','{}'));mid=cur.lastrowid
        check('real_bookmark_save',api('bookmarkMessage',str(mid),True)['ok'])
        check('real_bookmark_lookup',any(i['messageId']==mid for i in api('getBookmarks')))
        check('real_content_conversation_search',cid in api('searchConversations','LANTERN'))
        check('real_pin',api('pinChat',cid,True)['ok'] and next(i for i in api('getChats') if i['id']==cid)['pinned'])
        check('real_chat_rename',api('renameChat',cid,'QOL isolated conversation')['ok'])
        task('libraryManage',{'ids':[ids['delete-me']],'action':'hide'})
        if '--native' in sys.argv:
            # Start a real guarded request without awaiting its modal answer.
            expr="window.qolPermanentResult=null;window.offlineNative.workspaceRequest('libraryManage',"+json.dumps(json.dumps({'ids':[ids['delete-me']],'action':'purge','confirmed':True}))+",raw=>window.qolPermanentResult=JSON.parse(raw))"
            r=native_request(expr,'cancel')
            check('native_cancel_preserves_file',not r.get('ok') and (PROFILE/'generated/delete-me.png').is_file())
            r=native_request(expr,'confirm')
            if not r.get('ok'):raise RuntimeError(str(r))
            for _ in range(300):
                result=js('window.qolResults['+json.dumps(r['requestId'])+']')
                if result:break
                wait(50)
            check('native_confirmed_permanent_deletion',result.get('ok') and result['value']['completed']==1 and not (PROFILE/'generated/delete-me.png').exists())
            with db() as c:check('permanent_receipt_and_tombstone',c.execute('SELECT deleted FROM library_images WHERE id=?',(ids['delete-me'],)).fetchone()[0]==2 and c.execute("SELECT count(*) FROM library_file_events WHERE event='os_purge_success'").fetchone()[0]==1)
        with db() as c:
            check('unrelated_library_row_unchanged',c.execute('SELECT * FROM library_images WHERE id=?',(ids['unrelated'],)).fetchone()==unrelated_row)
            check('unrelated_pixels_unchanged',hashlib.sha256((PROFILE/'generated/unrelated.png').read_bytes()).hexdigest()==original['unrelated'])
            # Synthetic ambiguous interruption evidence; restart must preserve UNKNOWN.
            c.execute('INSERT INTO library_file_operations VALUES(?,?,?,?,?,?,?,?,?)',('qol-interrupted','qol',ids['parent'],'recycle',str(PROFILE/'generated/parent.png'),'prepared','Simulated interrupted operation',1,1))
        # Exercise UI draft restoration and an immediate close flush, without sending a model request.
        js("[...document.querySelectorAll('.history-item')].find(e=>e.textContent.includes('QOL isolated conversation')).click()");button('Chat');wait(200)
        check('ui_draft_restored',js("document.querySelector('textarea').value==='Persistent draft'"))
        js("(()=>{const e=document.querySelector('textarea');Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,'value').set.call(e,'Final close draft with unsent changes');e.dispatchEvent(new Event('input',{bubbles:true}));window.offlineNative.closeApp();})()")
        for _ in range(200):
            if process.poll() is not None:break
            wait(50)
        check('normal_close_flush',process.poll() is not None)
        with db() as c:check('unsent_draft_persisted_at_close',bool(c.execute("SELECT value FROM intelligence_meta WHERE key LIKE 'draft:%' AND value LIKE '%Final close draft%'").fetchone()))
except Exception as exc:
    report['error']=repr(exc);save();raise
finally:
    if process.poll() is None:check('normal_shutdown',close_normally())
    else:check('normal_shutdown',True)
    save()
sys.exit(any(not v for v in report['checks'].values()) or bool(report.get('error')))
