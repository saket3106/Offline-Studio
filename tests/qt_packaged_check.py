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
report={'checks':{},'launch_pid':process.pid};errors=[]
def check(name,passed):
    report['checks'][name]=bool(passed)
    if not passed:errors.append(name)
try:
    targets=[]
    for _ in range(100):
        if process.poll() is not None:raise RuntimeError('Installed executable exited during startup')
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1) as response:targets=json.load(response)
            if targets:break
        except Exception:pass
        wait(150)
    target=next(t for t in targets if t.get('type')=='page')
    ws.open(QUrl(target['webSocketDebuggerUrl']))
    connected=[];ws.connected.connect(lambda:connected.append(True))
    for _ in range(60):
        if connected:break
        wait(100)
    if not connected:raise RuntimeError('Cannot connect to installed Qt WebEngine')
    command('Page.enable');wait(1500)
    check('packaged_frontend_loaded',js("!!document.querySelector('.composer-shell')"))
    js("document.querySelector('.new-chat-button').click()");wait(350)
    js("document.querySelector('textarea').focus()")
    command('Input.insertText',{'text':'Explain TCP in one sentence.'});wait(100)
    check('composer_keyboard_input',js("!document.querySelector('.send-button').disabled"))
    started=time.perf_counter();js("document.querySelector('.send-button').click()")
    transforms=[];spinner_seen=False;first_answer=None
    while time.perf_counter()-started<180:
        wait(150)
        state=js("(()=>{const s=document.querySelector('.activity-spinner');const a=[...document.querySelectorAll('.assistant-markdown')].at(-1);return {spinner:s?getComputedStyle(s).transform:null,answer:a?.textContent||'',busy:!!document.querySelector('.stop-button')};})()")
        if state['spinner']:spinner_seen=True;transforms.append(state['spinner'])
        if state['answer'] and first_answer is None:first_answer=time.perf_counter()-started
        if spinner_seen and not state['busy']:break
    report['inference_seconds']=round(time.perf_counter()-started,3)
    report['first_answer_seconds']=round(first_answer,3) if first_answer is not None else None
    report['response']=state['answer']
    check('packaged_real_model_answer',bool(state['answer'] and not state['answer'].startswith('Error:') and not state['busy']))
    check('packaged_spinner_rotates',len(set(transforms))>4)
    check('packaged_spinner_stops',not state['spinner'])
    check('timing_metadata_visible',js("document.querySelector('.assistant-message .message-meta-info').textContent.includes('Worked for')"))
    js("document.querySelector('.history-row.active .history-item').click()");wait(250)
    check('timing_metadata_persists_after_reload',js("document.querySelector('.assistant-message .message-meta-info').textContent.includes('Worked for')"))
    js("document.querySelector('textarea').focus()")
    command('Input.insertText',{'text':'Write a detailed 600 word guide to reliable database migrations.'});wait(100)
    js("document.querySelector('.send-button').click()");wait(1100)
    check('second_request_started',js("!!document.querySelector('.stop-button')"))
    cancelled=time.perf_counter();js("document.querySelector('.stop-button').click()")
    for _ in range(150):
        if not js("!!document.querySelector('.stop-button')"):break
        wait(100)
    report['cancel_seconds']=round(time.perf_counter()-cancelled,3)
    check('real_cancellation_completes',js("!document.querySelector('.stop-button') && !document.querySelector('.activity-spinner')"))
    command('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
    check('qt_reduced_motion_emulation',js("matchMedia('(prefers-reduced-motion:reduce)').matches"))
    command('Emulation.setEmulatedMedia',{'features':[]})
    image=command('Page.captureScreenshot',{'format':'png'})
    (ROOT/'logs'/'packaged-desktop-check.png').write_bytes(base64.b64decode(image['data']))
    js("(()=>{const original=window.confirm;window.confirm=()=>true;try{document.querySelector('.history-row.active .history-action-btn.delete').click();}finally{window.confirm=original;}})()");wait(300)
    check('temporary_test_chat_removed',js("document.querySelector('.history-row.active')===null"))
except Exception as exc:report['exception']=str(exc);errors.append('probe_exception')
finally:
    report['checks']['normal_shutdown']=close_normally()
    ws.close()
if report['checks'].get('normal_shutdown'):
    process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
    wait(5000)
    check('reopened_executable_stays_running',process.poll() is None)
    check('reopened_normal_shutdown',close_normally())
report['failed_checks']=errors
(ROOT/'logs'/'packaged-desktop-check.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2,ensure_ascii=True))
sys.exit(bool(errors) or not report['checks']['normal_shutdown'])
