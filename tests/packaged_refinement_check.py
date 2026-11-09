"""Existing isolated executable + new external UI. Default: real bridge, SQLite/restart, no models/devices.

Explicit --native/--agent-only adds bounded existing Qwen3-4B acceptance.
Never installs, builds, mutates production or uses microphone/audio devices.
"""
import argparse,base64,hashlib,json,os,socket,subprocess,sys,time,traceback,urllib.request
from pathlib import Path
import psutil
P=Path(__file__).resolve().parents[2]
C=P/'Recovery/CandidateBuild20261028/dist/Offline GPT';exe=C/'Offline GPT.exe'
p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);p.add_argument('--native',action='store_true',help='One bounded existing Qwen3-4B chat/Agent/cancel probe, no devices');p.add_argument('--agent-only',action='store_true',help='Do not repeat the independently passed chat task');a=p.parse_args();a.native=a.native or a.agent_only
O=a.report_dir.resolve();O.mkdir(parents=True,exist_ok=False)
assert psutil.virtual_memory().available>=2*1024**3,'RESOURCE BLOCKED: 2 GiB required before packaged Qt startup'
from PySide6.QtCore import QCoreApplication,QEventLoop,QTimer,QUrl
from PySide6.QtWebSockets import QWebSocket
qt=QCoreApplication([]);ws=QWebSocket('http://localhost');replies={};seq=0;process=None;checks={};screens=[];started=time.monotonic();failure=None;owned={}
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
baseline=sha(P/'Application/Offline GPT.exe');config_before=sha(P/'Application/offline_gpt_config.json')
assert sha(exe)==baseline=='b268354e668af9e660e92912fba767b0f804ba9abd3f70edc1ef2a1a7c97a6f2'
profile=O/'profile';profile.mkdir()
model=P/'Models/Chat/Qwen3-4B-Q4_K_M.gguf'
config={'gpt_oss_gguf':'','voice_model_path':'','flux_model':'','chat_backend':'bundled','theme':'dark','backup_schedule_enabled':False,'image_output_directory':str(profile/'generated')}
if a.native:
    assert model.is_file(),'Existing Qwen3-4B file missing; downloads prohibited'
    config.update(gpt_oss_gguf=str(model),chat_model='Qwen3-4B',chat_context=2048,chat_max_output_tokens=384,reasoning_mode='quick',model_lifecycle_mode='balanced')
(profile/'offline_gpt_config.json').write_text(json.dumps(config))
resources=[];native_results=[]

def wait(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec()
def received(raw):
    v=json.loads(raw)
    if 'id' in v:replies[v['id']]=v
ws.textMessageReceived.connect(received)
def command(method,params=None,timeout=8):
    global seq
    seq+=1;rid=seq;ws.sendTextMessage(json.dumps({'id':rid,'method':method,'params':params or {}}));end=time.monotonic()+timeout
    while rid not in replies and time.monotonic()<end:wait(30)
    if rid not in replies:raise TimeoutError(method)
    r=replies.pop(rid)
    if r.get('error'):raise RuntimeError(r['error'])
    return r.get('result',{})
def js(code):
    r=command('Runtime.evaluate',{'expression':code,'returnByValue':True,'awaitPromise':True})
    if r.get('exceptionDetails'):raise RuntimeError(r['exceptionDetails'])
    return r.get('result',{}).get('value')
def api(name,*args):
    raw=js('new Promise(resolve=>window.offlineBridge['+json.dumps(name)+']('+','.join([*(json.dumps(a) for a in args),'resolve'])+'))')
    try:return json.loads(raw)
    except (ValueError,TypeError):return raw
def until(code,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        assert psutil.virtual_memory().available>=512*1024**2,'RAM stop'
        if js(code):return True
        wait(50)
    return False
def check(name,v):
    checks[name]=bool(v)
    if not v:raise AssertionError(name)
def click(css):return js('document.querySelector('+json.dumps(css)+')?.click()')
def shot(name):
    wait(200);data=command('Page.captureScreenshot',{'format':'png'})['data'];(O/(name+'.png')).write_bytes(base64.b64decode(data));screens.append(name+'.png')
def launch():
    global process,ws
    with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env=dict(os.environ,OFFLINE_GPT_DATA_DIR=str(profile),OFFLINE_GPT_CAPTURE_FITTED_PROMPTS='0',OFFLINE_GPT_SAVE_TRAINING_CANDIDATES='0',QTWEBENGINE_REMOTE_DEBUGGING=f'127.0.0.1:{port}',QTWEBENGINE_CHROMIUM_FLAGS='--remote-allow-origins=http://localhost --disable-gpu --disable-background-networking --disable-background-timer-throttling')
    out=(O/('stdout-'+str(len(owned))+'.log')).open('wb');err=(O/('stderr-'+str(len(owned))+'.log')).open('wb')
    process=subprocess.Popen([str(exe)],cwd=str(C),env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW);out.close();err.close();owned[process.pid]=psutil.Process(process.pid).create_time()
    targets=None;end=time.monotonic()+25
    while time.monotonic()<end:
        assert process.poll() is None,'Candidate exited before bridge startup'
        assert psutil.virtual_memory().available>=512*1024**2,'RAM stop'
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list',timeout=1) as r:targets=json.load(r)
            if targets:break
        except OSError:pass
        wait(100)
    assert targets,'No CDP target'
    ws.open(QUrl(next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page')))
    end=time.monotonic()+5
    while ws.state().value!=3 and time.monotonic()<end:wait(40)
    check('bridge_ready_'+str(len(owned)),until('!!window.offlineBridge&&!!document.querySelector(".runtime-statusbar")'))
def close():
    global seq
    if process and process.poll() is None:
        # closeApp is a void slot. The app can close CDP before a promise callback
        # returns; process exit, not a WebChannel reply, is its acknowledgement.
        children=[(child.pid,child.create_time()) for child in psutil.Process(process.pid).children(recursive=True)]
        seq+=1;ws.sendTextMessage(json.dumps({'id':seq,'method':'Runtime.evaluate','params':{'expression':'window.offlineBridge.closeApp()'}}))
        end=time.monotonic()+12
        while process.poll() is None and time.monotonic()<end:wait(50)
        check('normal_shutdown_'+str(len(owned)),process.poll() is not None)
        def still_owned(pid,born):
            try:return psutil.Process(pid).create_time()==born
            except psutil.NoSuchProcess:return False
        end=time.monotonic()+4
        while any(still_owned(pid,born) for pid,born in children) and time.monotonic()<end:wait(50)
        check('descendant_cleanup_'+str(len(owned)),not any(still_owned(pid,born) for pid,born in children))
    ws.close();wait(80)
def sample_resources(cool=False):
    import shutil
    cli=shutil.which('nvidia-smi')
    if not cli:raise RuntimeError('Native driver preflight unavailable')
    r=subprocess.run([cli,'--query-gpu=temperature.gpu,memory.used,memory.total,driver_version','--format=csv,noheader,nounits'],capture_output=True,text=True,timeout=5,creationflags=subprocess.CREATE_NO_WINDOW)
    if r.returncode:raise RuntimeError('NVIDIA driver query failed')
    fields=r.stdout.strip().splitlines()[0].split(',');temp=float(fields[0]);free=psutil.virtual_memory().available
    row={'wall':time.monotonic()-started,'availableRamGiB':free/1024**3,'gpuC':temp,'globalVramMiB':float(fields[1]),'totalVramMiB':float(fields[2]),'driver':fields[3].strip()};resources.append(row)
    assert temp<(70 if cool else 82),'GPU temperature safety stop'
    assert free>=512*1024**2,'512-MiB RAM stop'
    return row

def native_checks():
    import sqlite3,uuid
    row=sample_resources(cool=True)
    assert row['availableRamGiB']>=4,'RESOURCE BLOCKED: 4 GiB required after Qt startup'
    check('native_model_file_configured',api('getSettings')['gpt_oss_gguf']==str(model))
    dbpath=profile/'offline_gpt.sqlite3'
    def last():
        with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
            r=db.execute("SELECT id,content,metrics FROM messages WHERE role='assistant' ORDER BY id DESC LIMIT 1").fetchone()
            return {'id':r[0],'text':r[1],'metrics':json.loads(r[2] or '{}')} if r else {'id':0}
    def send(prompt):
        js('(()=>{const e=document.querySelector(".composer-shell textarea");Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype,"value").set.call(e,'+json.dumps(prompt)+');e.dispatchEvent(new Event("input",{bubbles:true}));})()')
        check('composer_accepts_'+str(len(native_results)),until('document.querySelector(".composer-shell textarea")?.value==='+json.dumps(prompt)))
        click('.send-button')
    def response(before,limit=75):
        start=time.monotonic();stream=False;next_sample=0
        while time.monotonic()-start<limit:
            if time.monotonic()>next_sample:sample_resources();next_sample=time.monotonic()+1
            stream=stream or bool(js('!!document.querySelector(".streaming-active")'))
            value=last()
            if value['id']>before and value.get('text') and not js('!!document.querySelector(".stop-button")') and not api('getAgentStatus').get('active'):
                value.update(wallSeconds=time.monotonic()-start,streamingObserved=stream);return value
            wait(80)
        api('stop');raise TimeoutError('Native response deadline')
    if not a.agent_only:
        marker='UI-'+uuid.uuid4().hex[:10]
        before=last()['id'];send('Write one short natural sentence about a quiet lake, and include the exact marker '+marker+'.');value=response(before);native_results.append(value)
        check('real_qwen_visible_canary',marker in value['text'])
        identity=value['metrics'].get('model_identity') or {}
        check('model_output_provenance',identity.get('outputSource')=='local_model' and identity.get('backend')=='bundled' and identity.get('nativeReady') is True and Path(identity.get('modelPath','')).resolve()==model.resolve() and identity.get('generatedTokens',0)>0)
        check('real_streaming_visible',value['streamingObserved']);shot('native-chat')
    workspace=O/'authorized-workspace';workspace.mkdir()
    granted=api('authorizeAgentWorkspace',str(workspace))
    check('only_synthetic_workspace_authorized',granted.get('ok') is True and Path(api('getAgentStatus')['workspace']).resolve()==workspace.resolve())
    js('[...document.querySelectorAll(".composer-mode-control button")].find(e=>e.textContent.trim()==="Agent").click()')
    check('agent_mode_selected',until('document.querySelector(".agent-mode-toggle")?.getAttribute("aria-pressed")==="true"'))
    before=last()['id'];send('Use the calculator tool to calculate 217 * 31. Report the result.');value=response(before);native_results.append(value)
    check('model_driven_calculator_answer',str(217*31) in value['text'])
    traces=value['metrics'].get('agent_traces') or []
    check('actual_mcp_calculator_trace',any(str(v.get('tool','')).endswith('calculate') and v.get('status') not in ['error','failed'] for v in traces));shot('native-agent')
    js('[...document.querySelectorAll(".composer-mode-control button")].find(e=>e.textContent.trim()==="Chat").click()')
    send('Write a detailed 2000-word explanation of how rivers shape landscapes.')
    check('cancel_button_available',until('!!document.querySelector(".stop-button")'));click('.stop-button')
    check('native_cancellation_settles',until('!document.querySelector(".stop-button")',15))
    sample_resources()

try:
    if a.native:sample_resources(cool=True)
    launch()
    if a.native:
        native_checks();close()
    else:
        check('candidate_uses_redesigned_assets',js('!!document.querySelector(".chat-greeting")&&getComputedStyle(document.querySelector(".chat-greeting")).fontFamily.includes("Georgia")'))
        check('real_settings_bridge',isinstance(api('getSettings'),dict))
        check('model_manager_bridge',api('getModelLibraryVersion')==1)
        check('actual_agent_registry',isinstance(api('getAgentStatus'),dict))
        shot('packaged-dark-empty')
        click('[title="Switch to light theme"]');check('real_theme_save',until('document.documentElement.dataset.theme==="light"'))
        check('theme_disk_readback',api('getAppearancePreferences')['preferences']['theme']=='light');shot('packaged-light-empty')
        click('[title="Models"]');check('models_destination',until('!!document.querySelector(".models-workspace .model-manager")'));shot('packaged-models')
        click('[title="Settings"]');check('settings_real_ui',until('!!document.querySelector(".settings-dialog")&&!!document.querySelector(".setting-field")'));shot('packaged-settings');click('[aria-label="Close settings"]')
        click('[title="Image studio"]');check('studio_real_ui',until('!!document.querySelector(".studio-preview")'));shot('packaged-studio')
        click('[title="Image Library"]');check('library_real_ui',until('!!document.querySelector(".library-view")'));shot('packaged-library')
        close();launch()
        check('restart_appearance_persistence',api('getAppearancePreferences')['preferences']['theme']=='light' and until('document.documentElement.dataset.theme==="light"'))
        close()
except Exception:failure=traceback.format_exc()
finally:
    # Graceful cleanup first. Never enumerate or terminate unrelated application processes.
    if process and process.poll() is None:
        try:close()
        except Exception:
            try:
                parent=psutil.Process(process.pid)
                if parent.create_time()==owned[process.pid]:
                    descendants=parent.children(recursive=True)
                    process.terminate();process.wait(timeout=5)
                    for child in descendants:
                        try:child.terminate()
                        except psutil.NoSuchProcess:pass
            except (psutil.NoSuchProcess,subprocess.TimeoutExpired):pass
    checks['production_exe_unchanged']=sha(P/'Application/Offline GPT.exe')==baseline
    checks['production_config_unchanged']=sha(P/'Application/offline_gpt_config.json')==config_before
    result={'scope':__doc__,'checks':checks,'failed':[n for n,v in checks.items() if not v],'failure':failure,'screenshots':screens,'seconds':time.monotonic()-started,'nativeProbeRequested':a.native,'nativeResults':native_results,'resourceSamples':resources,'microphoneCalls':0,'candidateExeSha256':sha(exe),'productionExeSha256':baseline,'ownedPids':list(owned)}
    (O/'packaged-refinement.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));sys.exit(bool(failure or result['failed']))
