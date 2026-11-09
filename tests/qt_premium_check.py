"""Probe the installed EXE through Qt's local DevTools protocol, then close it normally.
Creates and removes one temporary test chat. No persistent debugging setting is changed.
"""
import base64,json,os,subprocess,sys,time,urllib.request
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer,QUrl
from PySide6.QtWebSockets import QWebSocket
ROOT=Path(__file__).resolve().parents[1];PACKAGE=ROOT.parent/'Offline GPT'
app=QCoreApplication(sys.argv)
def wait(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
port=9237
env=dict(os.environ,QTWEBENGINE_REMOTE_DEBUGGING=f'127.0.0.1:{port}')
env['QTWEBENGINE_CHROMIUM_FLAGS']=(env.get('QTWEBENGINE_CHROMIUM_FLAGS','')+' --remote-allow-origins=http://localhost').strip()
process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
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
        subprocess.run(['powershell','-NoProfile','-Command',f'(Get-Process -Id {process.pid}).CloseMainWindow()'],capture_output=True,timeout=10)
        for _ in range(300):
            if process.poll() is not None:break
            wait(100)
    return process.poll() is not None

import sqlite3,uuid,ctypes
sys.path.insert(0,str(ROOT))
from integrated_runtime import physical_memory_status
mode='before' if '--before' in sys.argv else 'after'
gallery=ROOT/'logs'/('premium-'+mode);gallery.mkdir(exist_ok=True)
report={'launch_pid':process.pid,'mode':mode,'scenarios':[],'checks':{},'chats':[]}
if '--document-only' in sys.argv:report=json.loads((gallery/'report.json').read_text());report.pop('exception',None);report['chats']=[]
def shot(name):
    image=command('Page.captureScreenshot',{'format':'png'})
    (gallery/(name+'.png')).write_bytes(base64.b64decode(image['data']))
def submit(text):
    js("document.querySelector('textarea').focus()")
    command('Input.insertText',{'text':text});wait(100)
    js("document.querySelector('.send-button').click()")
def newchat():
    js("document.querySelector('.new-chat-button').click()");wait(250)
def current():
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        return db.execute('SELECT chat_id FROM messages ORDER BY id DESC LIMIT 1').fetchone()[0]
def metrics(cid):
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        rows=db.execute('SELECT role,content,metrics FROM messages WHERE chat_id=? ORDER BY id',(cid,)).fetchall()
        row=next((r for r in reversed(rows) if r[0]=='assistant'),None)
    return {'response':row[1], 'metrics':json.loads(row[2] or '{}')} if row else {}
def run(name,prompt):
    submitted_at=time.time();started=time.perf_counter();submit(prompt);wait(150)
    cid=current()
    if cid not in report['chats']:report['chats'].append(cid)
    first=None;peak=0;stages=[];busy_seen=False
    while time.perf_counter()-started<360:
        wait(140)
        state=js("(()=>{const a=[...document.querySelectorAll('.assistant-message')].at(-1);return {answer:a?.querySelector('.assistant-markdown')?.textContent||'',busy:!!document.querySelector('.stop-button'),status:a?.querySelector('[role=status]')?.textContent||'',image:!!a?.querySelector('.image-preview')};})()")
        busy_seen=busy_seen or state['busy']
        if state['status'] and state['status'] not in stages:
            stages.append(state['status'])
            if len(stages)<=2:shot(name+'-processing-'+str(len(stages)))
        peak=max(peak,physical_memory_status()['total']-physical_memory_status()['available'])
        if state['answer'] and first is None:first=time.perf_counter()-started
        if not state['busy']:
            with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
                finished=db.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='assistant' AND created>=?",(cid,submitted_at)).fetchone()[0]
            if finished:break
    elapsed=time.perf_counter()-started
    source_log=PACKAGE/'logs'/'llama-server.log'
    if source_log.exists():(gallery/(name+'-runtime.log')).write_text(source_log.read_text(errors='replace'),encoding='utf-8')
    shot(name)
    result={'name':name,'prompt':prompt,'wall_seconds':round(elapsed,3),'first_visible_seconds':round(first,3) if first else None,'peak_system_physical_used_bytes':peak,'stages':stages,'busy_at_end':state['busy'],**metrics(cid)}
    report['scenarios'].append(result)
    print(json.dumps({'name':name,'seconds':result['wall_seconds'],'first_visible_seconds':result['first_visible_seconds'],'error':result.get('response','')[:90] if result.get('response','').startswith(('Error:', 'Document error:', 'Image engine error:', 'Vision error:')) else None}),flush=True)
    (gallery/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return cid
try:
    targets=[]
    for _ in range(100):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1) as response:targets=json.load(response)
            if targets:break
        except Exception:pass
        wait(150)
    target=next(t for t in targets if t.get('type')=='page');ws.open(QUrl(target['webSocketDebuggerUrl']))
    connected=[];ws.connected.connect(lambda:connected.append(True))
    for _ in range(60):
        if connected:break
        wait(100)
    command('Page.enable');wait(1700)
    if '--document-only' not in sys.argv:
        newchat();run('A-cold-greeting','Hello there, how are you this morning?')
        newchat();run('B-next-chat-greeting','Hi again! How is your day going?')
    import pymupdf
    pdf=gallery/'context-probe.pdf';doc=pymupdf.open();page=doc.new_page();page.insert_text((50,65),'Harbour Observatory\nWeekly maintenance ledger\nCalibration interval: 17 days.\nOwner: Research Operations.');doc.save(pdf);doc.close()
    cid=str(uuid.uuid4());stamp=time.time()
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        db.execute('INSERT INTO chats(id,title,updated) VALUES(?,?,?)',(cid,'Premium document context probe',stamp))
        for role,content,path in [('user','Identify the attached PDF title.',str(pdf)),('assistant','The title is Harbour Observatory. '+('This maintenance document describes calibration checks and operator responsibilities. '*90),''),('user','Search this PDF for impossible phrase 45271.',str(pdf)),('assistant','NOT FOUND: impossible phrase 45271','')]:
            db.execute('INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)',(cid,role,content,stamp,path,''))
    report['chats'].append(cid)
    command('Page.reload');wait(1800)
    js("[...document.querySelectorAll('.history-item')].find(e=>e.textContent.includes('Premium document context probe')).click()");wait(250)
    run('C-document-chat-greeting','Hello! Nice to see you again.')
    if mode=='after':
        run('D-document-question','According to the attached PDF, what is the calibration interval and who owns it?')
        run('C2-warm-document-greeting','Hey there, how are you today?')
        run('D2-document-exact','Search the attached PDF for the exact phrase "Calibration interval". Return FOUND or NOT FOUND.')
        run('D3-document-exact','Search the attached PDF for the exact phrase "Cloud otters count 98217". Return FOUND or NOT FOUND.')
        report['checks']['all_document_timings_persist']=js("[...document.querySelectorAll('.assistant-message')].slice(-4).every(e=>e.textContent.includes('Worked for'))")
        js("document.querySelector('.history-row.active .history-item').click()");wait(200)
        report['checks']['document_timings_survive_reload']=js("[...document.querySelectorAll('.assistant-message')].slice(-4).every(e=>e.textContent.includes('Worked for'))")
        newchat();run('E-explanation','Explain in approximately 200 words how a local library can keep borrowing records correct when two desk clerks act simultaneously.')
        run('F-debugging','Debug this Python function. Explain the issue and return corrected code:\n```python\ndef labels(items):\n    output = []\n    for i in range(len(items) + 1):\n        output.append(items[i].strip())\n    return output\n```')
        js("[...document.querySelectorAll('button')].find(b=>b.title==='Switch to light theme').click()");wait(250);shot('light-chat-code')
        js("[...document.querySelectorAll('button')].find(b=>b.title==='Switch to dark theme').click()");wait(250)
        js("document.querySelector('.sidebar-close').click()");wait(300);shot('collapsed-sidebar')
        js("[...document.querySelectorAll('button')].find(b=>b.title==='Expand sidebar').click()");wait(250)
        js("[...document.querySelectorAll('.topbar button')].find(b=>b.title==='Settings').click()");wait(300);shot('settings')
        js("document.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))");wait(200)
    report['checks']['actual_qt_frontend']=True
except Exception as exc:
    report['exception']=str(exc);print(str(exc),flush=True)
finally:
    report['checks']['normal_shutdown']=close_normally();ws.close()
    # Remove only exact UUIDs created by this probe after shutdown.
    if report['checks']['normal_shutdown']:
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            for cid in report['chats']:
                db.execute('DELETE FROM messages WHERE chat_id=?',(cid,));db.execute('DELETE FROM chats WHERE id=?',(cid,))
    (gallery/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'mode':mode,'checks':report['checks'],'exception':report.get('exception')}))
sys.exit(bool(report.get('exception')))
