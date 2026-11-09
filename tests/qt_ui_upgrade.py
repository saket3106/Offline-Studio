"""Source Qt/React screenshots and bridge checks. Synthetic isolated profile, no inference."""
import argparse,json,os,sys,time,traceback
from pathlib import Path
from unittest.mock import patch
import psutil
p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--baseline',action='store_true');p.add_argument('--spot',action='store_true');p.add_argument('--scale',default='1');a=p.parse_args()
O=a.out.resolve();O.mkdir(parents=True,exist_ok=False);S=Path(__file__).resolve().parents[1]
assert psutil.virtual_memory().available>=2*1024**3,'2 GiB available RAM required'
profile=O/'profile';profile.mkdir();(profile/'offline_gpt_config.json').write_text(json.dumps({'gpt_oss_gguf':'','voice_model_path':'','flux_model':'','chat_backend':'bundled','theme':'dark','backup_schedule_enabled':False}))
os.environ.update(OFFLINE_GPT_DATA_DIR=str(profile),OFFLINE_GPT_CAPTURE_FITTED_PROMPTS='0',OFFLINE_GPT_SAVE_TRAINING_CANDIDATES='0',QTWEBENGINE_CHROMIUM_FLAGS='--disable-background-networking',QT_SCALE_FACTOR=a.scale)
sys.path.insert(0,str(S));import app
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtTest import QTest
from PySide6.QtWebEngineCore import qWebEngineChromiumVersion
qt=QApplication([]);guard=patch.object(app.EngineManager,'ensure_chat',side_effect=AssertionError('Native inference forbidden in UI fixture'));guard.start()
backend=app.App();backend.hide();window=app.DesktopWindow(backend);window.show();view=window.view
checks={};shots=[];failure=None
def js(code):
 v=[];loop=QEventLoop();view.page().runJavaScript('JSON.stringify((()=>{'+code+'})())',lambda x:(v.append(x),loop.quit()));QTimer.singleShot(5000,loop.quit);loop.exec();return json.loads(v[0]) if v and v[0] else None
def wait(code):
 end=time.monotonic()+12
 while time.monotonic()<end:
  if js('return '+code):return True
  assert psutil.virtual_memory().available>=512*1024**2
  QTest.qWait(70)
 return False
def check(k,v):
 checks[k]=bool(v)
 if not v:raise AssertionError(k)
def click(text,scope='.side-primary'):
 return js('const e=[...document.querySelectorAll('+json.dumps(scope+' button')+')].find(b=>b.textContent.trim().toLowerCase()==='+json.dumps(text.lower())+');if(!e)return false;e.click();return true')
def shot(name):
 js('window.__painted=false;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__painted=true));return true');assert wait('window.__painted');QTest.qWait(120);view.grab().save(str(O/(name+'.png')));shots.append(name+'.png')
try:
 check('qt_bridge',wait('!!window.offlineBridge&&!!document.querySelector(".composer-shell")'))
 for w,h in ([(960,600)] if a.spot else [(1280,800),(1920,1080),(2560,1440)]):
  window.resize(w,h);QTest.qWait(150)
  for theme in ['dark','light']:
   js('document.documentElement.dataset.theme='+json.dumps(theme)+';return true');shot(f'{w}x{h}-{theme}-chat')
   for label,selector in [('Projects','.project-workspace,.project-layout'),('Library','.library-view'),('Image studio','.creation-workspace'),('Models','.model-manager')]:
    check(f'{w}-{theme}-{label}',click(label) and wait('!!document.querySelector('+json.dumps(selector)+')'));shot(f'{w}x{h}-{theme}-{label.lower().replace(" ","-")}')
   js('document.querySelector(".new-chat-button").click()')
   js('document.querySelector(".sidebar-settings-btn").click();return true');check('settings_ready',wait('!!document.querySelector(".settings-dialog .setting-field")'));shot(f'{w}x{h}-{theme}-settings');js('document.querySelector("[aria-label=\\"Close settings\\"]").click();return true')
 if not a.baseline:
  before=len(backend.store.chats_with_updated())
  js('document.querySelector(".new-chat-button").click();return true');QTest.qWait(100)
  js('document.querySelector(".new-chat-button").click();return true');QTest.qWait(100)
  check('new_chat_draft_no_native_rows',len(backend.store.chats_with_updated())==before)
  window.resize(960,600);click('Image Studio') or click('Image studio');check('canvas_custom',wait('!!document.querySelector("[aria-label=\\"Studio canvas\\"][role=\\"combobox\\"]")'))
  check('no_native_selects',js('return document.querySelectorAll("select:not([aria-hidden=true])").length===0'))
  check('no_horizontal_overflow',js('return document.documentElement.scrollWidth<=innerWidth+1'))
  check('studio_small_window_no_nested_control_scroller',js('const e=document.querySelector(".studio-controls");return e.scrollHeight<=e.clientHeight+1'))
 check('no_model_calls',app.EngineManager.ensure_chat.call_count==0)
except Exception:
 failure=traceback.format_exc();print(failure)
finally:
 try:window.close();backend.close();QTest.qWait(250)
 except Exception:pass
 guard.stop();(O/'RESULT.json').write_text(json.dumps({'scope':'source Qt/React, isolated profile, zero inference; process-local scale, not global Windows setting','checks':checks,'failure':failure,'screenshots':shots,'chromium':qWebEngineChromiumVersion(),'requestedScale':a.scale,'devicePixelRatio':view.devicePixelRatioF()},indent=2))
sys.exit(1 if failure else 0)
