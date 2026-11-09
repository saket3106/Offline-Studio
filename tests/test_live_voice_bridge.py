"""Real Qt/App/WebChannel ownership with synthetic recognizer/playback, no AI/audio."""
import json,os,tempfile,time,unittest
from pathlib import Path
from unittest.mock import Mock,patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QObject,QThread,QTimer,Signal
from PySide6.QtWidgets import QApplication,QWidget
import app

class FakeSpeech(QObject):
 changed=Signal(dict)
 def __init__(self,parent):super().__init__(parent);self.state='ready';self.message_id='';self.token='';self.streaming=False;self.warmup_id='';self.shutdowns=0
 def snapshot(self):return {'state':self.state,'messageId':self.message_id,'operationId':self.token,'error':''}
 def emit(self):self.changed.emit(self.snapshot())
 def warmup(self):self.state='ready';self.emit()
 def stop(self):self.state='ready';self.streaming=False;self.emit()
 def shutdown(self):self.shutdowns+=1;self.stop()

class FakeWhisper(QThread):
 state=Signal(str);completed=Signal(str);failed=Signal(str)
 next_text='Synthetic question'
 def __init__(self,pcm,rate,cfg,parent=None,**kw):super().__init__(parent);self.metrics={};self.cancelled=False
 def cancel(self):self.cancelled=True
 def run(self):
  if not self.cancelled:self.completed.emit(self.next_text)

class BridgeTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.qt=QApplication.instance() or QApplication([])
 def wait(self,predicate,seconds=2):
  end=time.monotonic()+seconds
  while not predicate() and time.monotonic()<end:self.qt.processEvents();time.sleep(.005)
  self.assertTrue(predicate(),'Bounded Qt transition did not complete')
 def test_ten_automatic_turns_owned_capture_commands_and_chat_fences(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB_PATH',Path(folder)/'test.sqlite3'),patch.object(app,'DATA_DIR',Path(folder)),patch.object(app,'WhisperTranscriptionWorker',FakeWhisper):
   backend=app.App();window=QWidget();bridge=app.DesktopBridge(backend,window);backend.frontend_bridge=bridge
   speech=FakeSpeech(window);bridge.speech=speech;speech.changed.connect(bridge._speech_changed)
   backend.prewarm_whisper=Mock();submitted=[]
   def answer(text_override):
    submitted.append((backend.current,text_override));backend.set_busy(True,'Synthetic inference')
    backend.store.add(backend.current,'user',text_override)
    live=backend.live_voice_session;live.bind_response(str(len(submitted)))
    speech.message_id=str(len(submitted));speech.state='speaking';speech.emit()
    def complete():
     backend.store.add(backend.current,'assistant','Synthetic response')
     backend.set_busy(False,'Ready');speech.state='ready';speech.emit()
    QTimer.singleShot(5,complete)
   backend.send=answer
   try:
    result=json.loads(bridge.setLiveVoiceMode(True));self.assertTrue(result['ok']);live=backend.live_voice_session
    for i in range(10):
     self.wait(lambda:live.capture_requested)
     snapshot=live.snapshot();ack=json.loads(bridge.startLiveVoiceInput(live.session_id,live.generation));self.assertTrue(ack['ok'])
     self.assertFalse(backend.start_voice_input()['ok']) # Ordinary dictation cannot steal live capture.
     self.assertEqual(live.state,'listening');self.assertTrue(backend.voice_recording)
     duplicate=json.loads(bridge.startLiveVoiceInput(live.session_id,live.generation))
     self.assertTrue(duplicate['ok']);self.assertTrue(duplicate['alreadyStarted']);self.assertEqual(duplicate['turnId'],ack['turnId'])
     # A duplicate start must not corrupt the current recording/session.
     self.assertEqual(live.state,'listening')
     FakeWhisper.next_text=f'Question {i}'
     bridge.pushLiveVoiceAudio(live.session_id,ack['turnId'],__import__('base64').b64encode(b'\x10\x00'*6000).decode(),16000)
     bridge.stopLiveVoiceInput(live.session_id,ack['turnId'])
     bridge.stopLiveVoiceInput(live.session_id,ack['turnId'])
     self.wait(lambda:len(submitted)==i+1 and not backend.busy)
     backend._send_voice_turn(ack['turnId'],backend.current,FakeWhisper.next_text)
     self.assertEqual(len(submitted),i+1)
    self.assertEqual(len({t for _,t in submitted}),10);self.assertEqual(speech.shutdowns,0)
    self.wait(lambda:live.capture_requested)
    ack=json.loads(bridge.startLiveVoiceInput(live.session_id,live.generation));FakeWhisper.next_text='End this live voice mode.'
    bridge.pushLiveVoiceAudio(live.session_id,ack['turnId'],__import__('base64').b64encode(b'\x10\x00'*6000).decode(),16000)
    bridge.stopLiveVoiceInput(live.session_id,ack['turnId']);self.wait(lambda:not live.active)
    self.wait(lambda:backend.voice_worker is None)
    self.assertEqual(len(submitted),10);self.assertFalse(backend.voice_recording);self.assertFalse(bridge.live_voice_timer.isActive())
    self.assertEqual(backend.store.con.execute('SELECT count(*) FROM messages').fetchone()[0],20)
    self.assertEqual(backend.store.con.execute('PRAGMA quick_check').fetchone()[0],'ok')
    # Re-enter through the same real bridge and feed a natural transcript.
    # It must exit before LLM submission, then fence the obsolete session.
    bridge.setLiveVoiceMode(True);self.wait(lambda:live.capture_requested)
    natural_sid=live.session_id;natural_generation=live.generation
    ack=json.loads(bridge.startLiveVoiceInput(natural_sid,natural_generation))
    FakeWhisper.next_text='Okay, could you please end the voice chat now?'
    bridge.pushLiveVoiceAudio(natural_sid,ack['turnId'],__import__('base64').b64encode(b'\x10\x00'*6000).decode(),16000)
    bridge.stopLiveVoiceInput(natural_sid,ack['turnId']);self.wait(lambda:not live.active)
    self.wait(lambda:backend.voice_worker is None)
    self.assertEqual(len(submitted),10);self.assertFalse(backend.voice_recording);self.assertFalse(bridge.live_voice_timer.isActive())
    self.assertFalse(json.loads(bridge.startLiveVoiceInput(natural_sid,natural_generation))['ok'])
    bridge.setLiveVoiceMode(True);self.wait(lambda:live.capture_requested)
    sid=live.session_id;generation=live.generation;other=backend.store.new_chat('Other')
    bridge.loadChat(other);self.assertFalse(live.active)
    self.assertFalse(json.loads(bridge.startLiveVoiceInput(sid,generation))['ok'])
    self.assertEqual(backend.current,other)
   finally:
    bridge.setLiveVoiceMode(False)
    self.wait(lambda:backend.voice_worker is None)
    backend.frontend_bridge=None;backend.close();backend.store.con.close();window.close();self.qt.processEvents()

if __name__=='__main__':unittest.main()
