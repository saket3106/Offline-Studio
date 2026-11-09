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
mode='images-voice-sprint'
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
    js("window.premiumFrames=[];window.premiumFrameActive=true;window.premiumPrevious=null;function sample(t){if(window.premiumPrevious!=null)window.premiumFrames.push(t-window.premiumPrevious);window.premiumPrevious=t;if(window.premiumFrameActive)requestAnimationFrame(sample);}requestAnimationFrame(sample);")
    submitted_at=time.time();started=time.perf_counter();submit(prompt);wait(150)
    cid=current()
    if cid not in report['chats']:report['chats'].append(cid)
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        accepted=db.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='user' AND created>=?",(cid,submitted_at)).fetchone()[0]
    if not accepted:raise RuntimeError('Controller did not accept submitted request: '+name)
    first=None;peak=0;stages=[];image_states=[];percentages=[];busy_seen=False;measured_capture=False;preview_layouts=[]
    while time.perf_counter()-started<(900 if name=='image-generation' else 30):
        wait(140)
        state=js("(()=>{const a=[...document.querySelectorAll('.assistant-message')].at(-1);return {answer:a?.querySelector('.assistant-markdown')?.textContent||'',busy:!!document.querySelector('.stop-button'),status:a?.querySelector('[role=status]')?.textContent||'',image:!!a?.querySelector('.image-preview'),imageState:a?.querySelector('[data-image-state]')?.dataset.imageState||'',percentage:a?.querySelector('[role=progressbar]')?.getAttribute('aria-valuenow')||null};})()")
        busy_seen=busy_seen or state['busy']
        if state['imageState'] and state['imageState'] not in image_states:
            image_states.append(state['imageState']);shot(name+'-'+state['imageState'])
            preview_layouts.append(js("(()=>{const r=document.querySelector('.generation-surface')?.getBoundingClientRect();const d=document.querySelector('.image-dot-field')?.getBoundingClientRect();return {state:document.querySelector('[data-image-state]')?.dataset.imageState,width:r?.width,height:r?.height,dotHeight:d?.height,motion:document.querySelector('[data-motion]')?.dataset.motion};})()"))
        if state['percentage'] is not None:
            percentages.append(state['percentage'])
            if not measured_capture:
                shot(name+'-measured-sampling');measured_capture=True
        if state['status'] and state['status'] not in stages:
            stages.append(state['status'])
            if len(stages)<=2:shot(name+'-processing-'+str(len(stages)))
        peak=max(peak,physical_memory_status()['total']-physical_memory_status()['available'])
        if state['answer'] and first is None:first=time.perf_counter()-started
        if not state['busy']:
            with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
                finished=db.execute("SELECT COUNT(*) FROM messages WHERE chat_id=? AND role='assistant' AND created>=?",(cid,submitted_at)).fetchone()[0]
            if finished:break
    if state['busy']:raise RuntimeError('Controller remained busy after timeout: '+name)
    elapsed=time.perf_counter()-started
    frame_stats=js("(()=>{window.premiumFrameActive=false;const f=window.premiumFrames.slice(3).sort((a,b)=>a-b);return {count:f.length,median_ms:f[Math.floor(f.length*.5)],p95_ms:f[Math.floor(f.length*.95)],max_ms:f.at(-1)};})()")
    source_log=PACKAGE/'logs'/'llama-server.log'
    if source_log.exists():(gallery/(name+'-runtime.log')).write_text(source_log.read_text(errors='replace'),encoding='utf-8')
    shot(name)
    result={'frame_stats':frame_stats,'name':name,'prompt':prompt,'wall_seconds':round(elapsed,3),'first_visible_seconds':round(first,3) if first else None,'peak_system_physical_used_bytes':peak,'stages':stages,'image_states':image_states,'sampling_percentages':percentages,'preview_layouts':preview_layouts,'busy_at_end':state['busy'],**metrics(cid)}
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

    report['desktop_scaling']=js('({devicePixelRatio:devicePixelRatio,innerWidth:innerWidth,innerHeight:innerHeight})')
    newchat();image_cid=run('image-generation','Create a 512x320 image of a small modern astronomical observatory beside a quiet lake at dawn, realistic lighting, no text.')
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        row=db.execute("SELECT attachment FROM messages WHERE chat_id=? AND role='assistant' ORDER BY id DESC LIMIT 1",(image_cid,)).fetchone()
    from PIL import Image
    path=Path(row[0]) if row and row[0] else None
    report['checks']['live_image_saved_and_readable']=bool(path and path.is_file())
    if path and path.is_file():
        with Image.open(path) as result:report['image_output']={'path':str(path),'dimensions':list(result.size)};result.verify()
        report['final_preview_layout']=js("(()=>{const r=document.querySelector('.image-preview-wrapper').getBoundingClientRect();return {width:r.width,height:r.height};})()")
        preview=next((r for r in report['scenarios'][-1]['preview_layouts'] if r.get('width')),None)
        final=report['final_preview_layout']
        report['checks']['preview_matches_final']=bool(preview and abs(preview['width']-final['width'])<2 and abs(preview['height']-final['height'])<2)
        report['checks']['preview_fills_rectangle']=bool(preview and preview['height']>200 and preview['dotHeight']>120)
        report['checks']['image_read_aloud_available']=js("!!document.querySelector('.image-meta-actions [title=\"Read aloud offline\"]')")
        report['checks']['real_sampling_seen']='SAMPLING' in report['scenarios'][-1]['image_states']
        report['checks']['no_premature_100']=all(int(v)<100 for v in report['scenarios'][-1]['sampling_percentages'])
        js("document.querySelector('.prompt-accordion-toggle').click()");wait(150)
        js("document.querySelector('.prompt-copy-btn').click()");wait(150)
        report['checks']['prompt_copy_feedback']=js("document.querySelector('.image-prompt-accordion').textContent.includes('Copied')")
        shot('completed-image-details')
        js("document.querySelector('.history-row.active .history-item').click()");wait(180)
        report['checks']['image_persists_in_chat']=js("!!document.querySelector('.image-preview')")
        wait(350)
        report['image_layout']=js("(()=>{const v=document.querySelector('.conversation-viewport').getBoundingClientRect();const c=document.querySelector('.composer-shell').getBoundingClientRect();const a=document.querySelector('.image-actions-group')?.getBoundingClientRect();return {viewportBottom:v.bottom,composerTop:c.top,actionsTop:a?.top,actionsBottom:a?.bottom};})()")
        report['checks']['conversation_does_not_overlap_composer']=report['image_layout']['viewportBottom']<=report['image_layout']['composerTop']+1

    newchat();submitted=time.time();submit('Create a 512x320 photo of a mountain cabin in gentle autumn sunlight, no text.');wait(200)
    cancel_cid=current();report['chats'].append(cancel_cid)
    cancellation_start=None;started=time.perf_counter()
    while time.perf_counter()-started<120:
        wait(150)
        state=js("document.querySelector('[data-image-state]')?.dataset.imageState || ''")
        if state=='LOADING_MODEL':
            shot('image-cancel-before');cancellation_start=time.perf_counter();js("document.querySelector('[title=\"Stop image generation\"]').click()");break
        if not js("!!document.querySelector('.stop-button')"):break
    if cancellation_start:
        for _ in range(200):
            if not js("!!document.querySelector('.stop-button')"):break
            wait(100)
        report['cancel_seconds']=round(time.perf_counter()-cancellation_start,3)
    report['checks']['live_image_cancelled']=bool(cancellation_start and not js("!!document.querySelector('.stop-button')"))
    (gallery/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    shot('image-cancelled')
    # Four file tasks, then restart, proving metrics are stored individually.
    import pymupdf
    pdf=gallery/'timing-probe.pdf';doc=pymupdf.open();page=doc.new_page();page.insert_text((50,65),'Aurora Workshop\nReview interval: 23 days.\nOwner: Instrument Group.');doc.save(pdf);doc.close()
    cid=str(uuid.uuid4());stamp=time.time()
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        db.execute('INSERT INTO chats(id,title,updated) VALUES(?,?,?)',(cid,'Premium timing persistence probe',stamp))
        db.execute('INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)',(cid,'user','Attached document for testing.',stamp,str(pdf),''))
    report['chats'].append(cid);command('Page.reload');wait(1500)
    js("[...document.querySelectorAll('.history-item')].find(e=>e.textContent.includes('Premium timing persistence probe')).click()");wait(200)
    for i,phrase in enumerate(['Aurora Workshop','Review interval','Instrument Group','Imaginary observatory 34982']):
        run('pdf-timing-'+str(i+1),'Search the attached PDF for the exact phrase "'+phrase+'". Return FOUND or NOT FOUND.')
    report['checks']['four_pdf_times_visible']=js("[...document.querySelectorAll('.assistant-message')].length===4 && [...document.querySelectorAll('.assistant-message')].every(e=>e.textContent.includes('Worked for'))")
    shot('four-pdf-timings')
    with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
        saved=db.execute("SELECT metrics FROM messages WHERE chat_id=? AND role='assistant' ORDER BY id",(cid,)).fetchall()
    report['checks']['four_pdf_metrics_in_database']=len(saved)==4 and all(json.loads(r[0]).get('request_id') and json.loads(r[0]).get('duration_seconds') is not None for r in saved)
    report['checks']['shutdown_before_restart']=close_normally();ws.close();wait(200)
    replies.clear();connected.clear();process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
    for _ in range(100):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1) as response:targets=json.load(response)
            if targets:break
        except Exception:pass
        wait(150)
    ws.open(QUrl(next(t for t in targets if t.get('type')=='page')['webSocketDebuggerUrl']))
    for _ in range(60):
        if connected:break
        wait(100)
    command('Page.enable');wait(1200)
    js("[...document.querySelectorAll('.history-item')].find(e=>e.textContent.includes('Premium timing persistence probe')).click()");wait(250)
    report['checks']['four_pdf_times_survive_app_restart']=js("[...document.querySelectorAll('.assistant-message')].length===4 && [...document.querySelectorAll('.assistant-message')].every(e=>e.textContent.includes('Worked for'))")
    shot('four-pdf-timings-after-restart')
except Exception as exc:
    report['exception']=str(exc);print(str(exc),flush=True)
finally:
    report['checks']['normal_shutdown']=close_normally();ws.close()
    if report['checks']['normal_shutdown']:
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            for cid in report['chats']:
                db.execute('DELETE FROM messages WHERE chat_id=?',(cid,));db.execute('DELETE FROM chats WHERE id=?',(cid,))
    (gallery/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'checks':report['checks'],'exception':report.get('exception'),'image':report.get('image_output'),'cancel_seconds':report.get('cancel_seconds')}))
sys.exit(bool(report.get('exception')) or not all(report['checks'].values()))
