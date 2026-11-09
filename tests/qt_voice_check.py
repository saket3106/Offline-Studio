"""Real packaged bridge/audio probe; restores preferences and closes normally."""
import json, sqlite3, uuid, psutil
from pathlib import Path

# Reuse only the DevTools transport helpers, before its scenario setup.
exec((Path(__file__).with_name('qt_sprint_check.py')).read_text(encoding='utf-8').split('import sqlite3,uuid')[0])
gallery=ROOT/'logs/voice-image-sprint';gallery.mkdir(exist_ok=True)
report={'checks':{},'voices':[], 'peak_worker_ram':0,'peak_worker_cpu_percent':0}
cid=str(uuid.uuid4());config_path=PACKAGE/'offline_gpt_config.json'
config_before=config_path.read_bytes() if config_path.exists() else None
original=None; samples={}; message_id=None;targets=[]
cache_before={p.name for p in (PACKAGE/'kokoro/cache').glob('*')}
report['test_chat']=cid
config_before_path=gallery/'config-before-voice.json'
if config_before:config_before_path.write_bytes(config_before)
with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
    db.execute('INSERT INTO chats(id,title,updated) VALUES(?,?,?)',(cid,'Kokoro packaged verification',time.time()))
    text="Hello! I'm Offline GPT. I read answers with a natural offline voice. "+('This paragraph has careful punctuation, clear words and natural pauses. '*20)
    cursor=db.execute('INSERT INTO messages(chat_id,role,content,created,attachment,metrics) VALUES(?,?,?,?,?,?)',(cid,'assistant',text,time.time(),'','{}'))
    message_id=cursor.lastrowid

def close_normally():
    if process.poll() is None:
        try:
            subprocess.run(['powershell','-NoProfile','-Command','Get-Process -Name "Offline GPT" -ErrorAction SilentlyContinue | ForEach-Object { $_.CloseMainWindow() }'],capture_output=True,timeout=10)
        except Exception:pass
        for _ in range(100):
            if process.poll() is not None:break
            wait(100)
        if process.poll() is None:
            try:
                for c in psutil.Process(process.pid).children(recursive=True):
                    c.terminate()
                process.terminate()
            except Exception:pass
            for _ in range(50):
                if process.poll() is not None:break
                wait(100)
    return process.poll() is not None

def check(name,value):
    report['checks'][name]=bool(value)
    if not value:print('FAILED '+name,flush=True)

def api(method,*args):
    return js('new Promise(resolve=>window.voiceProbeBridge['+json.dumps(method)+']('+','.join(json.dumps(a) for a in args)+(',' if args else '')+'raw=>resolve(JSON.parse(raw))))')

def status():return api('getSpeechStatus')

def until(predicate,seconds=45):
    end=time.perf_counter()+seconds
    while time.perf_counter()<end:
        state=status()
        for p in psutil.process_iter(['name','cmdline']):
            try:
                if p.info['name']=='Offline GPT.exe' and '--speech-worker' in (p.info['cmdline'] or []):
                    report['peak_worker_ram']=max(report['peak_worker_ram'],p.memory_info().rss)
                    samples.setdefault(p.pid,p)
                    report['peak_worker_cpu_percent']=max(report['peak_worker_cpu_percent'],samples[p.pid].cpu_percent())
            except psutil.Error:pass
        if state.get('error'):raise RuntimeError(state['error'])
        if predicate(state):return state
        wait(100)
    raise RuntimeError('Audio timeout: '+str(state))

try:
    process=subprocess.Popen([str(PACKAGE/'Offline GPT.exe')],cwd=PACKAGE,env=env)
    for _ in range(150):
        try:
            targets=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=1).read())
            if targets:break
        except Exception:pass
    ws.open(QUrl(next(t for t in targets if t.get('type')=='page')['webSocketDebuggerUrl']))
    for _ in range(100):
        if ws.state() == QAbstractSocket.SocketState.ConnectedState: break
        wait(100)
    command('Page.enable');wait(1200)
    # Inspect the existing React bridge without installing another QWebChannel.
    check('existing_bridge',js("(()=>{const root=document.querySelector('#root');const f=root[Object.keys(root).find(k=>k.startsWith('__reactContainer$'))];const seen=new Set();function find(n){if(!n||seen.has(n))return null;seen.add(n);for(let h=n.memoizedState;h;h=h.next){if(h.memoizedState?.getSpeechStatus)return h.memoizedState;}return find(n.child)||find(n.sibling)||find(n.alternate);}window.voiceProbeBridge=find(f);return !!window.voiceProbeBridge;})()"))
    original=status();report['installed_voice_count']=len(original['voices']);check('kokoro_installed',original.get('kokoroInstalled'))
    api('speechSettings',json.dumps({'provider':'kokoro','voice':'af_heart','speed':1}))
    js("[...document.querySelectorAll('.history-item')].find(e=>e.textContent.includes('Kokoro packaged verification')).click()");wait(150)
    js("document.querySelector('[title=\"Read aloud offline\"]').click()")
    played=until(lambda s:s.get('position',0)>0);report['long_message_first_audio']=played['metrics']
    check('first_chunk_before_full_synthesis',len(played['metrics']['chunk_synthesis_ms'])<5)
    check('player_visible',js("!!document.querySelector('.speech-player')"))
    api('controlSpeech','pause');check('pause',status()['state']=='paused')
    api('speechSettings',json.dumps({'speed':1.25}));check('speed_preserves_pause',status()['state']=='paused')
    api('controlSpeech','resume');check('resume',status()['state']=='speaking')
    api('controlSpeech','stop');check('stop',status()['state']=='ready')
    api('controlSpeech','replay');check('replay',status()['state'] in ('loading','speaking'))
    api('controlSpeech','stop')
    continuity="Hello! I'm Offline GPT. I read answers with a natural offline voice. "+('The next sentence should begin smoothly, without overlapping voices. '*4)
    api('speakResponse',str(message_id),continuity)
    complete=until(lambda s:s['state']=='ready' and s['position']==s['length'],90)
    report['continuity_metrics']=complete['metrics']
    check('long_chunk_continuity',complete['metrics']['audio_underruns']==0)
    js("[...document.querySelectorAll('button')].find(e=>e.title==='Settings').click()");wait(150)
    js("[...document.querySelectorAll('.settings-nav button')].find(e=>e.textContent==='Read Aloud').click()");wait(150)
    check('settings_voice_menu',js("document.querySelectorAll('.voice-option').length>=28 && [...document.querySelectorAll('.voice-option')].every(e=>e.querySelector('button'))"))
    js("[...document.querySelectorAll('.voice-option')].find(e=>e.textContent.includes('Michael')).querySelector('button').click()")
    check('settings_preview_button',until(lambda s:s.get('position',0)>0)['voice']=='am_michael')
    import base64
    (gallery/'voice-settings.png').write_bytes(base64.b64decode(command('Page.captureScreenshot',{'format':'png'})['data']))
    api('controlSpeech','stop');js("document.querySelector('[title=\"Close settings\"]').click()");wait(100)
    for voice in ['af_heart','am_michael','bf_emma','bm_george']:
        api('previewVoice',voice)
        s=until(lambda s:s.get('position',0)>0)
        report['voices'].append({'voice':voice,'metrics':s['metrics']})
        check('preview_'+voice,s['voice']==voice)
        check('preview_preserves_default_'+voice,s['defaultVoice']=='af_heart')
        api('controlSpeech','stop')
    # Preview has no GPT call. New request must release local TTS first.
    check('preview_no_gpt_process',not any(p.info['name']=='llama-server.exe' for p in psutil.process_iter(['name'])))
    api('speakResponse',str(message_id),text);wait(250)
    js("document.querySelector('textarea').focus()");command('Input.insertText',{'text':'Hello!'});js("document.querySelector('.send-button').click()");wait(1000)
    check('new_request_stops_audio',status()['state']=='ready')
    check('new_request_releases_tts',not any(p.info['name']=='Offline GPT.exe' and '--speech-worker' in (p.info['cmdline'] or []) for p in psutil.process_iter(['name','cmdline'])))
    if js("!!document.querySelector('.stop-button')"):
        js("document.querySelector('.stop-button').click()")
        for _ in range(900):
            if not js("!!document.querySelector('.stop-button')"):break
            wait(100)
    screenshot=command('Page.captureScreenshot',{'format':'png'})
    import base64
    (gallery/'packaged-voice.png').write_bytes(base64.b64decode(screenshot['data']))
except Exception as exc:report['exception']=str(exc);print(str(exc),flush=True)
finally:
    if original:
        try:api('controlSpeech','stop');api('speechSettings',json.dumps({'provider':original['provider'],'voice':original.get('defaultVoice') or original['voice'],'speed':original['speed']}))
        except Exception:pass
    report['checks']['normal_shutdown']=close_normally();ws.close()
    if report['checks']['normal_shutdown']:
        with sqlite3.connect(PACKAGE/'offline_gpt.sqlite3') as db:
            db.execute('DELETE FROM messages WHERE chat_id=?',(cid,));db.execute('DELETE FROM chats WHERE id=?',(cid,))
        if config_before:config_path.write_bytes(config_before)
    cache_new=[p.name for p in (PACKAGE/'kokoro/cache').glob('*') if p.name not in cache_before and not p.name.startswith('preview-')]
    report['checks']['session_audio_cleaned']=not cache_new
    report['session_audio_leftovers']=cache_new
    (gallery/'packaged-voice.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report),flush=True)
sys.exit(bool(report.get('exception')) or not all(report['checks'].values()))
