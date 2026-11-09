"""Canonical desktop integration with an EXISTING synthetic profile, no AI models.

Actual Qt/React/bridge/SQLite and MCP stdio are exercised. Planner cancellation
uses a scripted plan. Native load, speech and microphone acceptance are excluded.
"""
import argparse,asyncio,hashlib,json,os,sys,time,uuid,threading
from pathlib import Path
from unittest.mock import patch
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
S=Path(__file__).resolve().parents[1];profile=a.profile.resolve();workspace=a.workspace.resolve();report=a.report.resolve()
assert profile.is_dir() and workspace.is_dir() and report.parent.is_dir()
assert not profile.is_relative_to(S.parent/'Offline GPT') and not profile.is_relative_to(S)
config=profile/'offline_gpt_config.json';original_config=config.read_bytes();cfg=json.loads(original_config)
assert not cfg.get('gpt_oss_gguf') and not cfg.get('voice_model_path') and not cfg.get('flux_model'),'Use only the retained empty synthetic profile'
os.environ.update(OFFLINE_GPT_DATA_DIR=str(profile),OFFLINE_GPT_CAPTURE_FITTED_PROMPTS='0',OFFLINE_GPT_SAVE_TRAINING_CANDIDATES='0',QT_QPA_PLATFORM='offscreen',QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu --disable-background-networking')
sys.path.insert(0,str(S));sys.path.insert(0,str(S/'tests'))
import app
from test_model_inspection import fixture
from agent_mcp import MCPRegistry,MCPClientManager
from agent_runtime import AgentRuntime
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QEventLoop,QTimer,QThread
from PySide6.QtTest import QTest
from PIL import Image
import fitz,psutil

qt=QApplication([]);backend=app.App();backend.hide();window=app.DesktopWindow(backend);window.resize(1366,900);window.show();view=window.view
checks={};receipts=[];started=time.monotonic();failure=None;prefix='integration-'+uuid.uuid4().hex[:8];created=[];closing_worker=None;messages_before=backend.store.con.execute('SELECT count(*) FROM messages').fetchone()[0]
packets=[];window.bridge.event.connect(lambda raw:packets.append(json.loads(raw)))
load_guard=patch.object(app.EngineManager,'ensure_chat',side_effect=AssertionError('AI model loading is prohibited in this test'));load_guard.start()
def js(code):
 values=[];loop=QEventLoop();view.page().runJavaScript('JSON.stringify((()=>{'+code+'})())',lambda v:(values.append(v),loop.quit()));QTimer.singleShot(4000,loop.quit);loop.exec()
 return json.loads(values[0]) if values and values[0] else None
def until(predicate,seconds=12):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  if predicate():return True
  QTest.qWait(40)
 return False
def dom(code,seconds=12):return until(lambda:js('return '+code),seconds)
def check(name,value):
 checks[name]=bool(value)
 if not value:raise AssertionError(name)
def click(label):return js("const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()==="+json.dumps(label)+");if(!b)return false;b.click();return true")
def action(args):
 response=json.loads(window.bridge.workspaceRequest('modelLibrary',json.dumps(args)));assert response['ok'],response
 rid=response['requestId'];assert until(lambda:any(e.get('type')=='workspaceResult' and e.get('requestId')==rid for e in packets))
 result=next(e for e in packets if e.get('type')=='workspaceResult' and e.get('requestId')==rid)
 assert until(lambda:not window.bridge.workspace_jobs)
 return result
def answer_dialog(button):
 remaining=[time.monotonic()+3]
 def answer():
  box=QApplication.activeModalWidget()
  if isinstance(box,QMessageBox):box.button(button).click()
  elif time.monotonic()<remaining[0]:QTimer.singleShot(30,answer)
 QTimer.singleShot(50,answer)
try:
 check('react_bridge_ready',dom("!!window.offlineBridge&&!!document.querySelector('.model-chip')"))
 for name in ['A','B']:
  file=workspace/(prefix+'-'+name+'.gguf');data=fixture([('general.architecture',8,'qwen3'),('general.name',8,'Integration fixture '+name),('tokenizer.chat_template',8,'{{ messages }}'),('general.file_type',4,15)])
  with file.open('xb') as stream:stream.write(data)
  created.append((file,hashlib.sha256(data).hexdigest()))
  r=action({'operation':'import','path':str(file)});check('actual_worker_import_'+name,r['ok'] and r['value']['weightsCopied'] is False)
  if name=='A':model_a=file;id_a=r['value']['id']
  else:model_b=file;id_b=r['value']['id']
 r=action({'operation':'discover','directory':str(workspace)});check('bounded_discovery_actual_paths',r['ok'] and str(model_a) in r['value']['paths'] and str(model_b) in r['value']['paths'] and r['value']['nativeCompatible'] is False)
 js("document.querySelector('.model-chip').click();")
 check('selector_imports_visible',dom("document.querySelector('.model-selector-list')?.textContent.includes('Integration fixture A')"))
 js("[...document.querySelectorAll('.model-option-btn')].find(e=>e.textContent.includes('Integration fixture A')).click();")
 check('new_chat_model_navigation',until(lambda:bool(backend.current) and backend.store.get_chat_model(backend.current)==str(model_a)))
 check('new_chat_model_chip_updates',dom("document.querySelector('.model-chip').textContent.includes('Integration fixture A')"))
 chat_a=backend.current
 chat_b=backend.store.new_chat(prefix+' conversation B',model_override=str(model_b));window.bridge.historyChanged.emit()
 check('second_chat_history_visible',dom("document.querySelector('.sidebar')?.textContent.includes("+json.dumps(prefix+' conversation B')+")"))
 js("[...document.querySelectorAll('.sidebar button')].find(e=>e.textContent.includes("+json.dumps(prefix+' conversation B')+")).click();")
 check('history_navigation_uses_real_bridge',until(lambda:backend.current==chat_b))
 check('closed_selector_tracks_conversation_override',dom("document.querySelector('.model-chip').textContent.includes('Integration fixture B')"))
 js("document.querySelector('.sidebar-settings-btn').click();");check('settings_open',dom("!!document.querySelector('.settings-dialog')"));click('Model Manager')
 check('model_manager_real_references',dom("document.querySelector('.model-manager')?.textContent.includes('Integration fixture B')"))
 def select_a():js("[...document.querySelectorAll('.model-manager-item')].find(e=>e.textContent.includes('Integration fixture A')).querySelector('.model-manager-actions button').click();")
 answer_dialog(QMessageBox.No);select_a()
 check('native_cancel_preserves_default',dom("document.querySelector('.model-manager [role=alert]')?.textContent.includes('Selection cancelled')") and app.load_config()['gpt_oss_gguf']=='')
 answer_dialog(QMessageBox.Yes);select_a()
 check('native_confirm_updates_default_cache',until(lambda:backend.engines.cfg.get('gpt_oss_gguf')==str(model_a) and backend.model==backend.engines.cfg.get('chat_model') and 'Integration fixture A' in backend.model))
 check('manager_refreshes_committed_default',dom("document.querySelector('.model-manager-guidance[role=status]')?.textContent.includes('Integration fixture A')&&document.querySelector('.model-manager')?.getAttribute('aria-busy')==='false'"))
 check('default_config_committed',app.load_config()['gpt_oss_gguf']==str(model_a))
 check('pinned_conversation_preserved',backend.store.get_chat_model(chat_b)==str(model_b))
 check('metadata_not_inference_claim',not backend.engines.chat_status()['loaded'] and not backend.engines.chat_status()['runtimeLoaded'])
 check('manager_distinguishes_loaded_from_default',dom("document.querySelector('.model-manager-guidance[role=status]')?.textContent.includes('Loaded: None')"))
 r=action({'operation':'remove','id':id_b});check('pinned_reference_removal_blocked',not r['ok'] and 'conversation uses' in r['error'])
 for width in [1366,960]:
  window.resize(width,900);QTest.qWait(80)
  check('manager_layout_'+str(width),js("const e=document.querySelector('.model-manager'),r=e.getBoundingClientRect();return r.left>=0&&r.right<=innerWidth+1&&e.scrollWidth<=e.clientWidth+1"))
 view.grab().save(str(report.with_suffix('.png')))
 # Genuine deterministic file/PDF/image metadata operations over the owned SDK.
 textfile=workspace/(prefix+'.txt');textfile.write_text('Reference token ORCHID-246. Total 579.\n',encoding='utf-8');created.append((textfile,hashlib.sha256(textfile.read_bytes()).hexdigest()))
 pdffile=workspace/(prefix+'.pdf');doc=fitz.open();page=doc.new_page();page.insert_text((72,72),'Offline integration PDF token CEDAR-357');doc.save(pdffile);doc.close();created.append((pdffile,hashlib.sha256(pdffile.read_bytes()).hexdigest()))
 imagefile=workspace/(prefix+'.png');Image.new('RGB',(13,17),'black').save(imagefile);created.append((imagefile,hashlib.sha256(imagefile.read_bytes()).hexdigest()))
 async def tools():
  async with MCPClientManager(workspace,interpreter=sys.executable) as client:
   calc=await client.call('calculate',{'expression':'83*7-2'});check('real_mcp_calculation',calc.get('value')==579)
   read=await client.call('read_local_file',{'path':textfile.name});check('real_mcp_file_read','ORCHID-246' in read.get('text',''))
   scoped=await client.call('read_local_file',{'path':textfile.name,'line_count':'1'});check('real_mcp_line_range',scoped.get('scoped_range') is True and scoped.get('end_line')==1 and 'ORCHID-246' in scoped.get('text',''))
   try:
    await client.call('read_local_file',{'path':textfile.name,'start_line':'invalid'});check('real_mcp_bad_range_rejected',False)
   except RuntimeError as exc:check('real_mcp_bad_range_rejected','Line ranges require' in str(exc))
   search=await client.call('search_workspace',{'query':'ORCHID-246'});check('real_mcp_literal_file_search','ORCHID-246' in json.dumps(search))
   pdf=await client.call('extract_pdf_text',{'path':pdffile.name});check('real_mcp_pdf_extraction','CEDAR-357' in json.dumps(pdf))
   meta=await client.call('inspect_file_metadata',{'path':imagefile.name});check('real_mcp_image_file_metadata',bool(meta) and 'error' not in meta)
   MCPRegistry.get_default().toggle_tool('calculate',False)
   try:
    await client.call('calculate',{'expression':'1+1'});check('disabled_tool_denied',False)
   except PermissionError:check('disabled_tool_denied',True)
   finally:MCPRegistry.get_default().toggle_tool('calculate',True)
  task=None
  def notify(event):
   if event['state']=='AWAITING_APPROVAL':task.cancel()
  task=AgentRuntime(lambda *_:json.dumps({'tool':'write_local_file','arguments':{'path':prefix+'-forbidden.txt','content':'must not be written'}}),workspace,None,'controlled',notify,interpreter=sys.executable,seconds=15)
  await task.run('Create a new test file')
  check('real_agent_cancellation_at_approval',task.state=='CANCELED' and not(workspace/(prefix+'-forbidden.txt')).exists())
 asyncio.run(tools())
 check('no_native_load_attempt',app.EngineManager.ensure_chat.call_count==0)
 check('conversation_messages_unchanged',backend.store.con.execute('SELECT count(*) FROM messages').fetchone()[0]==messages_before)
 check('source_profile_integrity',backend.store.con.execute('PRAGMA quick_check').fetchall()==[('ok',)])
 class ClosingWarmup(QThread):
  def __init__(self,parent):super().__init__(parent);self.release=threading.Event();self.cancelled=False
  def run(self):self.release.wait(3)
  def cancel(self):self.cancelled=True
 closing_worker=ClosingWarmup(backend);backend.voice_prewarm_worker=closing_worker;closing_worker.finished.connect(backend._voice_prewarm_finished);closing_worker.start();QTest.qWait(30)
 window.close();check('close_waits_for_owned_warmup',window.isVisible() and closing_worker.cancelled)
 closing_worker.release.set();check('close_completes_after_warmup',until(lambda:not window.isVisible() and backend.voice_prewarm_worker is None,5))
except Exception as exc:failure=str(exc)
finally:
 if closing_worker is not None:closing_worker.release.set()
 for _,worker in list(window.bridge.workspace_jobs.values()):worker.cancel_event.set()
 until(lambda:not window.bridge.workspace_jobs,5)
 MCPRegistry.get_default().toggle_tool('calculate',True)
 window.close();QTest.qWait(350);checks['normal_shutdown']=not window.isVisible()
 config.write_bytes(original_config)
 # Keep small fixtures as evidence; all created paths are explicit and bounded.
 checks['fixture_weights_and_sources_preserved']=all(hashlib.sha256(file.read_bytes()).hexdigest()==h for file,h in created)
 load_guard.stop()
 result={'scope':__doc__,'checks':checks,'failed':[n for n,v in checks.items() if not v],'failure':failure,'seconds':time.monotonic()-started,'nativeModelCalls':0,'liveMicrophoneCalls':0,'productionProfileUsed':False,'profileConfigRestored':config.read_bytes()==original_config,'fixturePaths':[str(f) for f,h in created]}
 report.write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
 if failure or result['failed']:raise SystemExit(1)
