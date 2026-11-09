import unittest
from live_voice import LiveVoiceSession,session_command

class SessionTests(unittest.TestCase):
 def setUp(self):
  self.now=0.;self.events=[];self.s=LiveVoiceSession(self.events.append,lambda:self.now)
 def ready(self):
  self.s.start('a');self.s.tick(chat='a',busy=False);return self.s
 def turn(self,s):
  turn=s.begin_capture(s.session_id,s.generation,'a',False,False)
  self.assertTrue(s.finalized(s.session_id,turn));return turn
 def test_ten_turns_at_most_once_and_actual_completion_before_rearm(self):
  s=self.ready();ids=[]
  for i in range(10):
   t=self.turn(s);ids.append(t);self.assertTrue(s.claim_submission(s.session_id,t))
   self.assertFalse(s.claim_submission(s.session_id,t))
   s.tick(chat='a',busy=False);self.assertFalse(s.capture_requested)
   s.tick(chat='a',busy=True);s.bind_response(str(i))
   s.tick(chat='a',busy=False,speech={'state':'speaking','messageId':str(i)})
   self.assertFalse(s.capture_requested)
   s.tick(chat='a',busy=False,speech={'state':'ready','messageId':str(i)})
   self.assertFalse(s.capture_requested);self.now+=.5;s.tick(chat='a',busy=False)
   self.assertTrue(s.capture_requested)
  self.assertEqual(len(set(ids)),10)
 def test_stop_ready_event_during_generation_never_opens_microphone(self):
  s=self.ready();t=self.turn(s);s.claim_submission(s.session_id,t)
  s.tick(chat='a',busy=True,speech={'state':'ready'})
  self.assertEqual(s.state,'thinking');self.assertFalse(s.capture_requested)
 def test_ordinary_task_is_not_bypassed(self):
  with self.assertRaisesRegex(ValueError,'active task'):self.s.start('a',True)
  s=self.ready()
  with self.assertRaises(ValueError):s.begin_capture(s.session_id,s.generation,'a',True,False)
 def test_chat_switch_fences_capture_and_transcript(self):
  s=self.ready();old=s.session_id;gen=s.generation;t=self.turn(s)
  s.tick(chat='b',busy=False);self.assertFalse(s.claim_submission(old,t))
  with self.assertRaises(ValueError):s.begin_capture(old,gen,'b',False,False)
 def test_close_restart_and_retry_fence_old_callbacks(self):
  s=self.ready();sid=s.session_id;gen=s.generation;s.close();s.start('a');s.tick(chat='a',busy=False)
  with self.assertRaises(ValueError):s.begin_capture(sid,gen,'a',False,False)
  sid=s.session_id;gen=s.generation;s.fail('device');s.retry();s.tick(chat='a',busy=False)
  with self.assertRaises(ValueError):s.begin_capture(sid,gen,'a',False,False)
 def test_failure_never_pretends_listening(self):
  s=self.ready();s.fail('recognizer failed');s.tick(chat='a',busy=False)
  self.assertEqual(s.state,'error');self.assertFalse(s.capture_requested)
 def test_muted_and_interrupt_cleanup_wait_for_real_workers(self):
  s=self.ready();s.mute(True);s.tick(chat='a',busy=False);self.assertFalse(s.capture_requested)
  s.mute(False);s.interrupt();s.tick(chat='a',busy=True);self.assertFalse(s.capture_requested)
  self.now=1;s.tick(chat='a',busy=False,stt_running=True);self.assertFalse(s.capture_requested)
  s.tick(chat='a',busy=False);self.assertTrue(s.capture_requested)
 def test_preparation_timeout_is_recoverable(self):
  s=self.s;s.start('a');self.now=61;s.tick(chat='a',busy=False,warming=True)
  self.assertEqual(s.state,'error');s.retry();s.tick(chat='a',busy=False);self.assertTrue(s.capture_requested)
 def test_older_actual_playback_still_excludes_microphone(self):
  s=self.ready();t=self.turn(s);s.claim_submission(s.session_id,t);s.bind_response('new')
  s.tick(chat='a',busy=True);s.tick(chat='a',busy=False,speech={'state':'speaking','messageId':'old'})
  self.now=1;s.tick(chat='a',busy=False,speech={'state':'speaking','messageId':'old'});self.assertFalse(s.capture_requested)
  s.tick(chat='a',busy=False);self.now+=.5;s.tick(chat='a',busy=False);self.assertTrue(s.capture_requested)
 def test_commands_are_exact_intents_not_quoted_content(self):
  for text,command in [('End this live voice mode.','exit'),('Stop live voice','exit'),('End this live voice model.','exit'),('Exit voice chat','exit'),('Stop talking!','interrupt'),('Pause listening','mute'),('Please resume listening.','unmute')]:
   self.assertEqual(session_command(text),command)
  for text in ['Explain "end voice mode"','Say stop talking','Do not end voice mode','The phrase end voice mode is an example','"End voice mode"','end voice mode and delete my files','Explain end this live voice model','"end this live voice model"','end this live voice model architecture','']:
   self.assertIsNone(session_command(text))

if __name__=='__main__':unittest.main()
