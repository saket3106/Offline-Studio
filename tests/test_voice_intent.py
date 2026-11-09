"""Hybrid command decisions, resident-only inference and actual Qt callback fences."""
import json,threading,time,unittest
from types import SimpleNamespace
from unittest.mock import Mock
from live_voice import session_command,voice_intent_candidate,classify_voice_intent

class VoiceIntentTests(unittest.TestCase):
 def test_positive_whole_utterances(self):
  for text in ['Exit the voice chat.','Please end the voice chat now.',"Okay, we're done talking.",'You can close voice mode.',"Let's finish this conversation.",'Can you stop the voice session?']:
   with self.subTest(text=text):self.assertEqual(session_command(text),'exit')
  self.assertEqual(session_command('Stop listening for now.'),'mute')
 def test_negative_and_ordinary_utterances_never_request_classifier(self):
  for text in ['How do I end the voice chat?',"Don't end the voice chat.",'Explain the exit command.','What happens if I stop voice mode?','I told someone to close their voice chat.','Your voice sounds soothing.','Tell me more about the car.']:
   with self.subTest(text=text):self.assertIsNone(session_command(text));self.assertFalse(voice_intent_candidate(text))
 def test_casual_closure_requires_confirmation(self):
  # 2026-11-09 owner rule: clear farewells end Live Voice; a bare "I'm done" still asks first.
  self.assertEqual(session_command("Thanks, I'm done for today."),'exit')
  self.assertIsNone(session_command("Okay, I'm done."));self.assertTrue(voice_intent_candidate("Okay, I'm done."))
 def engine(self,answer):
  runtime=SimpleNamespace(ready=True,context=2048,complete=Mock(return_value=answer))
  engine=SimpleNamespace(runtime=runtime,cfg={'chat_backend':'bundled'},loaded_model='resident-fixture',resource_lock=threading.RLock(),lock=threading.RLock(),_cancel_idle_timer=Mock(),_schedule_idle_unload=Mock(),_active_inference_count=0)
  return engine
 def test_resident_classification_does_not_load_or_switch_model(self):
  e=self.engine('{"intent":"EXIT_VOICE","confidence":"high"}');result=classify_voice_intent(e,'Please cease this voice session.',threading.Event())
  self.assertEqual(result['action'],'exit');self.assertEqual(e._active_inference_count,0);self.assertEqual(e.runtime.complete.call_count,1);self.assertEqual(e.runtime.complete.call_args.kwargs['allowed_tools'],[])
 def test_no_resident_model_is_clarification_without_inference(self):
  e=self.engine('');e.runtime.ready=False;r=classify_voice_intent(e,'Please cease this voice session.',threading.Event());self.assertEqual(r['intent'],'UNCERTAIN');e.runtime.complete.assert_not_called()
 def test_ordinary_conversation_has_zero_added_model_calls(self):
  e=self.engine('');r=classify_voice_intent(e,'Describe the car.',threading.Event());self.assertEqual(r['intent'],'NORMAL_CONVERSATION');e.runtime.complete.assert_not_called()
 def test_invalid_or_adversarial_output_cannot_execute_control(self):
  for answer in ['{"intent":"EXIT_VOICE","confidence":"high","tool":"delete"}','{"intent":"EXIT_VOICE","intent":"MUTE","confidence":"high"}','{"intent":"PC_CONTROL","confidence":"high"}','not JSON']:
   e=self.engine(answer);r=classify_voice_intent(e,'Please cease this voice session.',threading.Event());self.assertIsNone(r['action']);self.assertEqual(e._active_inference_count,0)
 def test_high_confidence_vague_goodbye_is_still_uncertain(self):
  r=classify_voice_intent(self.engine('{"intent":"EXIT_VOICE","confidence":"high"}'),"Okay, I'm done.",threading.Event());self.assertEqual(r['intent'],'UNCERTAIN');self.assertIsNone(r['action'])
 def test_canceled_classification_never_controls_session(self):
  c=threading.Event();c.set();e=self.engine('');r=classify_voice_intent(e,'Please cease this voice session.',c);self.assertIsNone(r['action']);e.runtime.complete.assert_not_called()
 def test_actual_qt_stale_intent_callback_cannot_close_new_session(self):
  import os;os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
  import app
  from live_voice import LiveVoiceSession
  live=LiveVoiceSession(lambda _:None);live.start('new-chat');worker=SimpleNamespace(cancel_event=threading.Event())
  backend=SimpleNamespace(voice_intent_worker=worker,voice_profiles={'old-turn':{}},live_voice_session=live,current='new-chat',frontend_bridge=Mock(),_save_voice_profile=Mock())
  app.App._voice_intent_done(backend,worker,'old-turn','old-chat','old-session','end voice',{'action':'exit'})
  backend.frontend_bridge.liveVoiceControl.assert_not_called();backend._save_voice_profile.assert_not_called()

 def clarification_owner(self,ok=True):
  import app
  from live_voice import LiveVoiceSession
  live=LiveVoiceSession(lambda _:None);live.start('chat');live.capture_requested=True
  turn=live.begin_capture(live.session_id,live.generation,'chat',False,False);live.finalized(live.session_id,turn)
  backend=SimpleNamespace(live_voice_session=live,voice_profiles={turn:{'status':'success'}},current='chat',busy=False,voice_worker=None,frontend_bridge=SimpleNamespace(speakResponse=Mock(return_value=json.dumps({'ok':ok,'error':'fixture unavailable'}))),_save_voice_profile=Mock())
  return app,backend,live,turn
 def test_clarification_claims_one_turn_and_playback_failure_is_explicit(self):
  app,b,live,turn=self.clarification_owner(False)
  app.App._clarify_voice_intent(b,turn,'chat',live.session_id)
  self.assertEqual(live.state,'error');self.assertFalse(live.capture_requested);self.assertFalse(live.pending_intent)
  b.frontend_bridge.speakResponse.assert_called_once()
 def test_clarification_has_one_confirmable_session_scoped_response(self):
  app,b,live,turn=self.clarification_owner(True)
  app.App._clarify_voice_intent(b,turn,'chat',live.session_id);app.App._clarify_voice_intent(b,turn,'chat',live.session_id)
  self.assertEqual(live.pending_intent,'exit');self.assertTrue(b.voice_profiles[turn]['liveSubmitted']);b.frontend_bridge.speakResponse.assert_called_once()
 def test_stale_clarification_cannot_speak_in_new_session(self):
  app,b,live,turn=self.clarification_owner(True);sid=live.session_id;live.close();live.start('chat')
  app.App._clarify_voice_intent(b,turn,'chat',sid);b.frontend_bridge.speakResponse.assert_not_called()

 def test_failed_classifier_reports_elapsed_time_and_releases_lease(self):
  e=self.engine('')
  def fail(*args,**kwargs):time.sleep(.02);raise RuntimeError('synthetic inference failure')
  e.runtime.complete.side_effect=fail
  result=classify_voice_intent(e,'Please cease this voice session.',threading.Event())
  self.assertEqual(result['intent'],'UNCERTAIN');self.assertGreaterEqual(result['classificationMs'],10);self.assertEqual(e._active_inference_count,0)

if __name__=='__main__':unittest.main()
