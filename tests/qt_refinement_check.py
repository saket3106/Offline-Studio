"""Real source Qt/React/WebChannel with isolated SQLite; zero native inference/device calls.

Synthetic message events are presentation fixtures, not model acceptance.
"""
import argparse,json,os,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
import psutil
p=argparse.ArgumentParser();p.add_argument('--report-dir',type=Path,required=True);a=p.parse_args()
O=a.report_dir.resolve();O.mkdir(parents=True,exist_ok=False)
assert psutil.virtual_memory().available>=2*1024**3,'RESOURCE BLOCKED: 2 GiB available required before Qt startup'
profile=O/'profile';profile.mkdir()
(profile/'offline_gpt_config.json').write_text(json.dumps({'gpt_oss_gguf':'','voice_model_path':'','flux_model':'','chat_backend':'bundled','theme':'dark','backup_schedule_enabled':False}))
os.environ.update(OFFLINE_GPT_DATA_DIR=str(profile),OFFLINE_GPT_CAPTURE_FITTED_PROMPTS='0',OFFLINE_GPT_SAVE_TRAINING_CANDIDATES='0',QT_QPA_PLATFORM='windows',QTWEBENGINE_CHROMIUM_FLAGS='--disable-background-networking --disable-background-timer-throttling --disable-renderer-backgrounding --disable-backgrounding-occluded-windows --disable-features=CalculateNativeWinOcclusion')
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S));import app
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtTest import QTest
qt=QApplication([]);backend=app.App();backend.hide();window=app.DesktopWindow(backend);window.resize(1440,960);window.show();view=window.view
from PIL import Image,ImageDraw
fixture_dir=profile/'generated';fixture_dir.mkdir(exist_ok=True)
fixture_image=fixture_dir/'synthetic-ui-preview.png'
canvas=Image.new('RGB',(320,180),'#292929');ImageDraw.Draw(canvas).rectangle((70,45,250,135),fill='#aaaaaa');canvas.save(fixture_image)
backend.store.index_library_image(str(fixture_image),prompt='Synthetic UI preview fixture',model='Presentation fixture',native_dimensions='320 × 180',final_dimensions='320 × 180')
backend.store.index_library_image(str(fixture_image).replace('\\','/'),prompt='Synthetic UI preview fixture',model='Presentation fixture',native_dimensions='320 × 180',final_dimensions='320 × 180')
checks={};screens=[];viewports=[];started=time.monotonic();failure=None
guard=patch.object(app.EngineManager,'ensure_chat',side_effect=AssertionError('No native models in desktop fixture checks'));guard.start()
def js(code):
    values=[];loop=QEventLoop();view.page().runJavaScript('JSON.stringify((()=>{'+code+'})())',lambda v:(values.append(v),loop.quit()));QTimer.singleShot(4000,loop.quit);loop.exec()
    return json.loads(values[0]) if values and values[0] else None
def wait(code,seconds=10):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        assert psutil.virtual_memory().available>=512*1024**2,'RAM safety stop'
        if js('return '+code):return True
        QTest.qWait(50)
    return False
def check(name,value):
    checks[name]=bool(value)
    if not value:raise AssertionError(name)
def click(selector):return js('const e=document.querySelector('+json.dumps(selector)+');if(!e)return false;e.click();return true')
def button(text,scope='document'):
    return js('const e=[...'+scope+'.querySelectorAll("button")].find(b=>b.textContent.trim()==='+json.dumps(text)+');if(!e)return false;e.click();return true')
def text(selector,value):
    return js('const e=document.querySelector('+json.dumps(selector)+');if(!e)return false;Object.getOwnPropertyDescriptor(e.tagName==="TEXTAREA"?HTMLTextAreaElement.prototype:HTMLInputElement.prototype,"value").set.call(e,'+json.dumps(value)+');e.dispatchEvent(new Event("input",{bubbles:true}));return true')
def shot(name):
    js('window.__verifiedPaint=0;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__verifiedPaint=1));return true')
    assert wait('window.__verifiedPaint===1',5),'No compositor paint; refuse stale screenshot'
    view.update();QTest.qWait(100);path=O/(name+'.png');view.grab().save(str(path));screens.append(path.name)
def emit(data):window.bridge.event.emit(json.dumps(data));QTest.qWait(150)
try:
    check('real_webchannel_ready',wait('!!window.offlineBridge&&!!document.querySelector(".composer-shell")'))
    check('editorial_greeting',js('return parseFloat(getComputedStyle(document.querySelector(".chat-greeting")).fontSize)>=32'))
    check('true_black_canvas',js('return getComputedStyle(document.querySelector(".chat-workspace")).backgroundColor==="rgb(0, 0, 0)"'))
    check('statusbar_bottom_row',js('const r=document.querySelector(".runtime-statusbar").getBoundingClientRect();return Math.abs(r.bottom-innerHeight)<2&&r.height===30'))
    shot('dark-empty-chat')
    window.showMaximized();QTest.qWait(200)
    check('maximized_composer_fits',js('const r=document.querySelector(".composer-shell").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth&&r.bottom<=innerHeight'))
    shot('dark-maximized-chat');window.showNormal();QTest.qWait(120)
    click('[title="Switch to light theme"]');check('theme_saved_through_real_bridge',wait('document.documentElement.dataset.theme==="light"') and app.load_config()['theme']=='light')
    check('offwhite_canvas',js('return getComputedStyle(document.querySelector(".chat-workspace")).backgroundColor==="rgb(252, 252, 251)"'));shot('light-empty-chat')
    click('.sidebar-settings-btn');check('settings_dialog_open',wait('!!document.querySelector(".settings-dialog")'))
    check('settings_has_fields',wait('!!document.querySelector(".setting-field")'))
    shot('settings-models-chat')
    for label in ['Model Manager','Runtime status','Voice input','Read aloud','Memory','Model paths','Compute & memory','Image generation','Enhancement','Backup & recovery','Appearance']:
        check('settings_navigation_'+label,button(label,'document.querySelector(".settings-nav")') and wait('document.querySelector(".settings-page-heading h2")?.textContent==='+json.dumps(label)))
    shot('settings-appearance')
    check('settings_fields_fit',js('const e=document.querySelector(".settings-content");return e.scrollWidth<=e.clientWidth+1'))
    text('[aria-label="Search settings"]','no-such-setting-123');check('settings_search_empty_feedback',wait('!!document.querySelector(".settings-no-results")'))
    text('[aria-label="Search settings"]','recognition');check('settings_search_description',wait('!![...document.querySelectorAll(".settings-nav button")].find(b=>b.textContent.includes("Voice input"))'))
    click('[aria-label="Close settings"]');check('settings_closed',wait('!document.querySelector(".settings-dialog")'))
    click('.sidebar-settings-btn');check('settings_search_reset',wait('document.querySelector(".settings-search input")?.value===""'))
    button('Appearance','document.querySelector(".settings-nav")');wait('!!document.querySelector(".appearance-workbench")')
    # Choose Dark in the single theme control (saved through the appearance bridge), then prove modal close does not undo it.
    click('.theme-segment [data-value="dark"]');check('appearance_saved',wait('document.querySelector(".theme-segment [data-value=dark]")?.getAttribute("aria-checked")==="true"'))
    click('[aria-label="Close settings"]');check('appearance_survives_close',wait('document.documentElement.dataset.theme==="dark"') and app.load_config()['theme']=='dark')
    click('[title="Search commands"]');check('command_palette_opens',wait('!!document.querySelector(".command-dialog")'))
    check('command_search_focused',wait('document.activeElement===document.querySelector(".command-search input")'))
    text('.command-search input','models');check('command_filter',wait('document.querySelector(".command-search input")?.value==="models"&&document.querySelectorAll(".command-results button").length===1&&document.querySelector(".command-results")?.textContent.includes("Model Manager")'))
    shot('command-palette');js('document.querySelector(".command-search input").dispatchEvent(new KeyboardEvent("keydown",{key:"Enter",bubbles:true}));return true')
    check('models_primary_destination',wait('!!document.querySelector(".models-workspace .model-manager")'))
    shot('models')
    button('Image studio','document.querySelector(".side-primary")');check('studio_two_panel',wait('!!document.querySelector(".studio-preview")'))
    check('studio_actual_file_preview',wait('document.querySelector(".studio-stage img")?.naturalWidth===320'))
    check('studio_aliases_do_not_duplicate_previews',js('return document.querySelectorAll(".studio-recent button").length===1'));shot('image-studio')
    text('#studio-description','a quiet observatory');button('Review in chat');check('studio_review_does_not_generate',wait('document.querySelector(".composer-shell textarea")?.value.includes("a quiet observatory")') and app.EngineManager.ensure_chat.call_count==0)
    text('[aria-label="Message input"]','Line one\nLine two\nLine three\nLine four\nLine five');QTest.qWait(150)
    check('composer_expands',js('return document.querySelector(".composer-shell textarea").getBoundingClientRect().height>90'));shot('expanded-composer')
    button('Projects','document.querySelector(".side-primary")');check('projects_real_view',wait('!!document.querySelector(".project-workspace")||!!document.querySelector(".project-layout")||document.querySelector(".main-panel").textContent.includes("New project")'));shot('projects')
    button('Library','document.querySelector(".side-primary")');check('library_real_view',wait('!!document.querySelector(".library-view")'))
    check('library_fixture_single_canonical_card',wait('document.querySelectorAll(".library-card").length===1'));shot('library')
    js('document.querySelector(".new-chat-button").click()');wait('!!document.querySelector(".composer-shell")')
    cid=backend.store.new_chat('Synthetic presentation fixture');backend.current=cid
    emit({'type':'chatChanged','id':cid,'messages':[{'id':'u','role':'user','content':'Show a small function and table.'},{'id':'a','role':'assistant','content':'## Synthetic rendering fixture\n\n```python\ndef double(value):\n    return value * 2\n```\n\n| Item | Value |\n| --- | --- |\n| Example | 42 |','metrics':{'agent_traces':[{'tool':'calculate','arguments':{'expression':'6*7'},'result':{'value':42},'status':'success','durationMs':2}]}}]})
    check('markdown_code_and_table',wait('!!document.querySelector(".code-block")&&!!document.querySelector("table")'))
    shot('chat-code-table-dark')
    check('agent_trace_fixture',js('return !!document.querySelector(".agent-trace-container")'))
    # Real registry/state display. No planner/model request is sent.
    button('Agent','document.querySelector(".composer-mode-control")')
    check('agent_context_connected',wait('!!document.querySelector(".agent-workspace-panel")'))
    shot('agent-workspace')
    click('[aria-label="Close context"]')
    button('Chat','document.querySelector(".composer-mode-control")')
    # Explicitly presentation-only; captureRequested=False prevents microphone access.
    emit({'type':'liveVoiceSession','chatId':cid,'sessionId':'presentation-fixture','generation':1,'revision':1,'active':True,'state':'paused','muted':True,'captureRequested':False})
    check('voice_state_fixture',wait('!!document.querySelector(".live-voice-dock[data-state=paused]")'))
    shot('voice-paused-fixture')
    emit({'type':'liveVoiceSession','chatId':cid,'sessionId':'presentation-fixture','generation':1,'revision':2,'active':False,'state':'idle','muted':False,'captureRequested':False})
    for width,height in [(1100,760),(800,640),(520,700)]:
        window.resize(width,height);QTest.qWait(200)
        viewports.append({'requestedWindow':[width,height],'actualWindow':[window.width(),window.height()],'webViewport':js('return [innerWidth,innerHeight]')})
        click('[title="Collapse sidebar"]');QTest.qWait(100)
        check('main_fits_'+str(width),js('const e=document.querySelector(".main-panel"),r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&e.scrollWidth<=e.clientWidth+1'))
        click('[title="Workspace context"]');check('inspector_visible_'+str(width),wait('!!document.querySelector(".context-inspector:not([hidden])")'))
        check('inspector_fits_'+str(width),js('const r=document.querySelector(".context-inspector").getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1'))
        shot('responsive-'+str(width));click('[aria-label="Close context"]')
    check('zero_model_calls',app.EngineManager.ensure_chat.call_count==0)
    check('sqlite_integrity',backend.store.con.execute('PRAGMA quick_check').fetchall()==[('ok',)])
except Exception:
    failure=traceback.format_exc();shot('failure')
finally:
    for _,worker in list(window.bridge.workspace_jobs.values()):worker.cancel_event.set()
    end=time.monotonic()+5
    while window.bridge.workspace_jobs and time.monotonic()<end:QTest.qWait(50)
    window.close();QTest.qWait(700);checks['normal_shutdown']=not window.isVisible()
    guard.stop()
    result={'scope':__doc__,'checks':checks,'failed':[k for k,v in checks.items() if not v],'failure':failure,'seconds':time.monotonic()-started,'screenshots':screens,'viewports':viewports,'qtDevicePixelRatio':view.devicePixelRatioF(),'nativeInferenceCalls':0,'microphoneCalls':0,'productionProfileUsed':False}
    (O/'qt-refinement.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));sys.exit(bool(failure or result['failed']))
