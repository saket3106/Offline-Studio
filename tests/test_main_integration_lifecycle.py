"""Turn ownership and Model Manager commits; no native model/microphone work."""
import json,threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app

class VoiceTurnTests(unittest.TestCase):
 def owner(self):
  b=SimpleNamespace(voice_turn_id='turn-a',voice_chat_id='chat-a',current='chat-a',voice_mode_active=True,busy=False,voice_profiles={'turn-a':{'status':'recognizing','stages':{},'finalizedEpochMs':1}},store=SimpleNamespace(workspace=Mock()),emit_frontend=Mock(),_save_voice_profile=Mock(),send=Mock())
  from live_voice import LiveVoiceSession
  live=LiveVoiceSession(lambda _:None);live.start('chat-a');live.tick(chat='chat-a',busy=False)
  turn=live.begin_capture(live.session_id,live.generation,'chat-a',False,False)
  live.finalized(live.session_id,turn)
  b.live_voice_session=live;b.voice_turn_id=turn
  b.voice_profiles={turn:{'status':'recognizing','stages':{},'finalizedEpochMs':1,'liveSessionId':live.session_id}}
  b.send=Mock(side_effect=lambda **kw:setattr(b,'busy',True))
  b._send_voice_turn=lambda *a:app.App._send_voice_turn(b,*a)
  return b
 def queued(self,b):
  callbacks=[]
  with patch.object(app.QTimer,'singleShot',side_effect=lambda _,fn:callbacks.append(fn)):app.App.voice_transcription_done(b,'Recognized request')
  self.assertEqual(len(callbacks),1);return callbacks[0]
 def test_exit_before_timer_does_not_send(self):
  b=self.owner();callback=self.queued(b);b.voice_mode_active=False;callback();b.send.assert_not_called()
 def test_new_chat_before_timer_does_not_send(self):
  b=self.owner();callback=self.queued(b);b.current='chat-b';callback();b.send.assert_not_called()
 def test_cancelled_turn_before_timer_does_not_send(self):
  b=self.owner();callback=self.queued(b);b.voice_turn_id='turn-b';callback();b.send.assert_not_called()
 def test_new_busy_operation_is_not_replaced(self):
  b=self.owner();callback=self.queued(b);b.busy=True;callback();b.send.assert_not_called()
 def test_normal_current_turn_submits_once(self):
  b=self.owner();callback=self.queued(b);callback();callback();b.send.assert_called_once_with(text_override='Recognized request')
 def test_duplicate_completion_does_not_create_second_timer(self):
  b=self.owner();self.queued(b)
  with patch.object(app.QTimer,'singleShot') as timer:app.App.voice_transcription_done(b,'Recognized request')
  timer.assert_not_called()
 def test_interrupt_cleanup_error_cannot_skip_cancellation(self):
  b=SimpleNamespace(busy=True,voice_mode_active=True,cancel_current=Mock(),cancel_voice_input=Mock())
  bridge=SimpleNamespace(backend=b,speech=Mock(),_cancel_pending_speech=Mock(),event=Mock())
  bridge.speech.stop.side_effect=RuntimeError('playback failure')
  result=json.loads(app.DesktopBridge.interruptVoice(bridge))
  self.assertFalse(result['ok']);b.cancel_current.assert_called_once();b.cancel_voice_input.assert_called_once();bridge._cancel_pending_speech.assert_called_once()
  self.assertFalse(b.voice_mode_active)
 def test_async_read_aloud_error_is_visible_in_live_mode_without_false_listening(self):
  backend=SimpleNamespace(voice_mode_active=True,busy=False,store=SimpleNamespace(workspace=Mock()))
  bridge=SimpleNamespace(backend=backend,speech_operation=None,event=Mock())
  app.DesktopBridge._speech_changed(bridge,{'state':'error','error':'controlled synthesis failure','operationId':'speech-request'})
  events=[json.loads(c.args[0]) for c in bridge.event.emit.call_args_list]
  self.assertTrue(any(e['type']=='voiceError' and 'controlled synthesis failure' in e['message'] for e in events))
  self.assertFalse(any(e.get('value')=='listening' for e in events))

class ModelCommitTests(unittest.TestCase):
 def test_default_commit_refreshes_desktop_cache_without_rewriting_chats(self):
  store=SimpleNamespace(workspace=Mock(),set_chat_model=Mock())
  engine=SimpleNamespace(cfg={'chat_model':'New selected default'},chat_status=Mock(return_value={'modelName':'New selected default'}))
  b=SimpleNamespace(store=store,engines=engine,model='Old selected default',ready=Mock())
  b.refresh_models=lambda:app.App.refresh_models(b)
  bridge=SimpleNamespace(backend=b,workspace_finished_ids=set(),event=Mock(),historyChanged=Mock())
  packet={'requestId':'selection','action':'modelLibrary','ok':True,'value':{'selected':True,'committed':True}}
  with patch.object(app,'ROUTER_MODEL','Old selected default'),patch.object(app,'models',return_value=['New selected default']):app.DesktopBridge._workspace_done(bridge,json.dumps(packet))
  self.assertEqual(b.model,'New selected default');store.set_chat_model.assert_not_called()
  self.assertTrue(any(json.loads(c.args[0]).get('type')=='modelHealth' for c in bridge.event.emit.call_args_list))
 def test_busy_conversation_selection_is_rejected(self):
  bridge=SimpleNamespace(backend=SimpleNamespace(busy=True,store=Mock()),workspace_jobs={},workspace_finished_ids=set(),historyChanged=Mock())
  result=json.loads(app.DesktopBridge.setChatModel(bridge,'chat-a','other'))
  self.assertFalse(result['ok']);bridge.backend.store.set_chat_model.assert_not_called()
 def test_missing_conversation_selection_is_not_reported_as_success(self):
  store=Mock();store.chats.return_value=[('exists','A')]
  bridge=SimpleNamespace(backend=SimpleNamespace(busy=False,store=store),workspace_jobs={},workspace_finished_ids=set(),historyChanged=Mock())
  result=json.loads(app.DesktopBridge.setChatModel(bridge,'missing','other'))
  self.assertFalse(result['ok']);store.set_chat_model.assert_not_called()

if __name__=='__main__':unittest.main()
