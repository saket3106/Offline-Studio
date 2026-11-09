"""Probe the installed EXE through Qt's local DevTools protocol, then close it normally.
Creates and removes one temporary test chat. No persistent debugging setting is changed.
"""
import base64,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer,QUrl
from PySide6.QtWebSockets import QWebSocket
from PySide6.QtNetwork import QAbstractSocket
ROOT=Path(__file__).resolve().parents[1];PACKAGE=ROOT.parent/'Offline GPT'
app=QCoreApplication(sys.argv)
def wait(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
port=9237
env=dict(os.environ,QTWEBENGINE_REMOTE_DEBUGGING=f'127.0.0.1:{port}')
env['QTWEBENGINE_CHROMIUM_FLAGS']=(env.get('QTWEBENGINE_CHROMIUM_FLAGS','')+' --remote-allow-origins=http://localhost').strip()
process=None
ws=QWebSocket('http://localhost');replies={};sequence=0;events=[]
def message(raw):
    value=json.loads(raw)
    if 'id' in value:replies[value['id']]=value
    else:
        events.append(value)
        if value.get('method')=='Page.javascriptDialogOpening':
            ws.sendTextMessage(json.dumps({'id':999999,'method':'Page.handleJavaScriptDialog','params':{'accept':True}}))
ws.textMessageReceived.connect(message)
def command(method,params=None,timeout=15):
    global sequence
    sequence+=1;request_id=sequence
    ws.sendTextMessage(json.dumps({'id':request_id,'method':method,'params':params or {}}))
    end=time.perf_counter()+timeout
    while request_id not in replies and time.perf_counter()<end:wait(20)
    if request_id not in replies:raise RuntimeError('DevTools timed out: '+method)
    result=replies.pop(request_id)
    if result.get('error'):raise RuntimeError(str(result['error']))
    return result.get('result',{})
def js(code):
    result=command('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True})
    if result.get('exceptionDetails'):raise RuntimeError(str(result['exceptionDetails']))
    return result.get('result',{}).get('value')
def close_normally():
    if process.poll() is None:
        try:
            js("window.offlineNative?.closeApp ? window.offlineNative.closeApp() : null")
        except Exception:
            pass
        subprocess.run(['powershell','-NoProfile','-Command',f'(Get-Process -Id {process.pid}).CloseMainWindow()'],capture_output=True,timeout=10)
        for _ in range(300):
            if process.poll() is not None:break
            wait(100)
    return process.poll() is not None


import sqlite3,uuid
report={'checks':{},'operations':[],'test_chats':[]}
gallery=ROOT/'logs/sprint-packaged';gallery.mkdir(exist_ok=True)
with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
    before={r[0] for r in db.execute('SELECT id FROM chats')}
    for title in ['Sprint UI A','Sprint UI B','Sprint PDF probe']:
        cid=str(uuid.uuid4());report['test_chats'].append(cid)
        db.execute('INSERT INTO chats(id,title,updated) VALUES(?,?,?)',(cid,title,time.time()))
        db.execute('INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)',
            (cid,'user','Test fixture for the sprint.',time.time(),r'C:\Users\mesak\Downloads\SELF_LEARNING_Alex_Doe_Final.pdf' if 'PDF' in title else '', '{}'))
        db.execute('INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)',
            (cid,'assistant','A local read-aloud playback check. '+('This sentence exercises the voice controls. '*20),time.time(),'','{"duration_seconds":2.5}'))
process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
report['launch_pid']=process.pid

def require(name,value):
    report['checks'][name]=bool(value)
    if not value:print('CHECK FAILED '+name,flush=True)
def screenshot(name):
    value=command('Page.captureScreenshot',{'format':'png'})
    (gallery/(name+'.png')).write_bytes(base64.b64decode(value['data']))
def click_label(label):js('[...document.querySelectorAll("button")].find(e=>e.title==='+json.dumps(label)+').click()');wait(150)
def field(selector,text):
    js('document.querySelector('+json.dumps(selector)+').focus()');command('Input.insertText',{'text':text});wait(200)
def search(text):
    js('(()=>{const e=document.querySelector(".history-search");const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,"value").set;setter.call(e,'+json.dumps(text)+');e.dispatchEvent(new Event("input",{bubbles:true}));})()');wait(250)
def open_chat(title):
    search(title);js('[...document.querySelectorAll(".history-item")].find(e=>e.textContent.includes('+json.dumps(title)+')).click()');wait(250)
def last():
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        row=db.execute("SELECT chat_id,content,metrics FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
    return {'chat_id':row[0],'answer':row[1],'metrics':json.loads(row[2] or '{}')} if row else {}
def submit(text):
    started=time.perf_counter();cid=report['test_chats'][2]
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        prior=db.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='assistant'",(cid,)).fetchone()[0]
    field('textarea',text);js('document.querySelector(".send-button").click()');wait(200)
    end=time.perf_counter()+160
    while time.perf_counter()<end:
        wait(150)
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            rows=db.execute("SELECT content,metrics FROM messages WHERE chat_id=? AND role='assistant' ORDER BY id",(cid,)).fetchall()
        if len(rows)>prior and not js('!!document.querySelector(".stop-button")'):
            result={'prompt':text,'answer':rows[-1][0],'metrics':json.loads(rows[-1][1] or '{}'),'wall_seconds':time.perf_counter()-started}
            report['operations'].append(result);return result
    raise RuntimeError('Timed out waiting for submitted request')
try:
    end=time.perf_counter()+25
    while time.perf_counter()<end:
        try:
            targets=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1).read());target=next(t for t in targets if t.get('type')=='page');break
        except Exception:wait(150)
    ws.open(QUrl(target['webSocketDebuggerUrl']))
    for _ in range(150):
        if ws.state()==QAbstractSocket.SocketState.ConnectedState:break
        wait(100)
    if ws.state()!=QAbstractSocket.SocketState.ConnectedState:raise RuntimeError('DevTools websocket connection failed: '+ws.errorString())
    command('Page.enable');wait(1200)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        new=[r[0] for r in db.execute('SELECT id FROM chats') if r[0] not in before and r[0] not in report['test_chats']]
        report['test_chats']+=new
    require('startup',js('!!document.querySelector("textarea")'))
    require('O_brand',js('document.querySelector(".brand-mark svg path").getAttribute("d").startsWith("M16 4C22.2")'))
    open_chat('Sprint UI A');click_label('Read aloud offline');wait(1500)
    require('offline_voice_playback',js('!!document.querySelector(".speech-player")'))
    click_label('Pause speech');require('voice_pause',js('[...document.querySelectorAll("button")].some(e=>e.title==="Resume speech")'))
    click_label('Resume speech');click_label('Stop speech');require('voice_stop',js('!document.querySelector(".speech-player")'))
    search('Sprint UI');click_label('Select chats');js('[...document.querySelectorAll(".chat-selection button")].find(e=>e.textContent==="Select all shown").click()');wait(100)
    require('select_filtered_two',js('document.querySelectorAll(".chat-select-row input:checked").length===2'))
    screenshot('selection');js('[...document.querySelectorAll(".chat-selection button")].find(e=>e.textContent==="Delete").click()');wait(500)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        require('bulk_trash_two',all(db.execute('SELECT 1 FROM chat_trash WHERE chat_id=?',(cid,)).fetchone() for cid in report['test_chats'][:2]))
        require('unrelated_preserved',db.execute('SELECT 1 FROM chats WHERE id=?',(report['test_chats'][2],)).fetchone())
    click_label('Recently deleted');search('Sprint UI');js('[...document.querySelectorAll(".chat-selection button")].find(e=>e.textContent==="Select all shown").click()');wait(100)
    js('[...document.querySelectorAll(".chat-selection button")].find(e=>e.textContent==="Restore").click()');wait(300)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        require('restore_two',not any(db.execute('SELECT 1 FROM chat_trash WHERE chat_id=?',(cid,)).fetchone() for cid in report['test_chats'][:2]))
    js('[...document.querySelectorAll(".chat-selection button")].find(e=>e.textContent==="Cancel").click()');wait(150)
    open_chat('Sprint PDF probe')
    for phrase,page in [('Sample values for illustration only.',8),('Replace the percentages with actual Google Forms results if survey responses are collected.',29),('Purple satellites manufacture invisible bicycles 7391',None)]:
        result=submit('Search the attached PDF for the exact phrase "'+phrase+'".')
        require('exact_'+str(page),('PDF page '+str(page) in result['answer']) if page else result['answer'].startswith('NOT FOUND'))
        require('zero_model_'+str(page),result['metrics'].get('model_calls')==0)
    screenshot('exact-document')
    if '--skip-semantic' not in sys.argv:
        result=submit('According to the attached PDF, are the performance comparison and questionnaire results actual measurements or illustrative examples? Cite pages.')
        require('grounded_document_answer','illustrat' in result['answer'].lower() and '8' in result['answer'] and '29' in result['answer'])
        require('bounded_prompt',result['metrics'].get('prompt_tokens',9999)<2000)
        screenshot('grounded-document')
    result=submit('Hello')
    require('pdf_greeting',not result['answer'].startswith('Error:') and result['metrics'].get('prompt_tokens',9999)<300)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        cid=report['test_chats'][2];old=db.execute('SELECT id,metrics FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone();old_count=db.execute('SELECT COUNT(*) FROM messages WHERE chat_id=?',(cid,)).fetchone()[0]
    click_label('Regenerate latest response');wait(250)
    for _ in range(700):
        wait(100)
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:new_metrics=json.loads(db.execute('SELECT metrics FROM messages WHERE id=?',(old[0],)).fetchone()[0] or '{}')
        if new_metrics.get('response_versions') and not js('!!document.querySelector(".stop-button")'):break
    require('regenerate_preserves_old',len(new_metrics.get('response_versions',[]))==1)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:require('regenerate_no_duplicate_turn',db.execute('SELECT COUNT(*) FROM messages WHERE chat_id=?',(cid,)).fetchone()[0]==old_count)
    require('version_navigation',js('!!document.querySelector(".response-versions")'));screenshot('response-versions')
    require('timing_all_responses',js('[...document.querySelectorAll(".assistant-message")].every(e=>e.textContent.includes("Worked for"))'))
    field('textarea','Explain TCP in detail.');js('document.querySelector(".send-button").click()');wait(300);js('document.querySelector(".stop-button").click()')
    for _ in range(600):
        wait(100)
        if not js('!!document.querySelector(".stop-button")'):break
    require('cancellation',js('!document.querySelector(".stop-button")'))
    open_chat('Sprint UI A');open_chat('Sprint PDF probe')
    require('timing_after_chat_switch',js('[...document.querySelectorAll(".assistant-message")].every(e=>e.textContent.includes("Worked for"))'))
    report['first_normal_shutdown']=close_normally();require('normal_close_before_restart',report['first_normal_shutdown'])
    if report['first_normal_shutdown']:
        ws.close();wait(250)
        process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
        report['restart_pid']=process.pid
        for _ in range(150):
            wait(150)
            try:
                targets=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1).read())
                target=next(t for t in targets if t.get('type')=='page');break
            except Exception:continue
        ws.open(QUrl(target['webSocketDebuggerUrl']))
        for _ in range(150):
            if ws.state()==QAbstractSocket.SocketState.ConnectedState:break
            wait(100)
        if ws.state()!=QAbstractSocket.SocketState.ConnectedState:raise RuntimeError('Restart DevTools websocket failed: '+ws.errorString())
        command('Page.enable');wait(1200)
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            report['test_chats'] += [r[0] for r in db.execute('SELECT id FROM chats') if r[0] not in before and r[0] not in report['test_chats']]
        open_chat('Sprint PDF probe')
        require('timing_after_restart',js('[...document.querySelectorAll(".assistant-message")].every(e=>e.textContent.includes("Worked for"))'))
        require('versions_after_restart',js('!!document.querySelector(".response-versions")'))
        screenshot('restart')

finally:
    report['normal_shutdown']=close_normally()
    if report['normal_shutdown']:
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            for cid in report['test_chats']:
                if cid in before:continue
                db.execute('DELETE FROM messages WHERE chat_id=?',(cid,));db.execute('DELETE FROM chats WHERE id=?',(cid,));db.execute('DELETE FROM chat_trash WHERE chat_id=?',(cid,))
            remaining={r[0] for r in db.execute('SELECT id FROM chats')}
            report['checks']['preexisting_chats_preserved']=before.issubset(remaining)
    (ROOT/'logs/sprint-packaged-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report['checks']))
