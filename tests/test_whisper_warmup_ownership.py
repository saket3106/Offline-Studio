"""Real QThread lifecycle with a controlled worker; no Whisper/model execution."""
import os,threading,time,unittest
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from unittest.mock import patch,Mock
from PySide6.QtCore import QObject,QThread,Signal,Slot
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
import app

class ControlledWarmup(QThread):
 failed=Signal(str)
 def __init__(self,pcm,rate,cfg,parent,prewarm_only=False):
  super().__init__(parent);assert QThread.currentThread()==parent.thread()
  self.release=threading.Event();self.failed_message=None;self.cancelled=False;self.prewarm_only=prewarm_only
 def run(self):
  self.release.wait(2)
  if self.failed_message:self.failed.emit(self.failed_message)
 def cancel(self):self.cancelled=True;self.release.set()

class Owner(QObject):
 def __init__(self):
  super().__init__();self.current='chat-a';self.voice_mode_active=True;self.voice_worker=None;self.voice_profiles={};self.voice_turn_id='turn';self.voice_lock=threading.Lock();self.voice_audio=bytearray(b'audio');self.voice_recording=True;self.events=[]
 def emit_frontend(self,event):self.events.append(event)
 @Slot(str)
 def _voice_prewarm_failed(self,error):app.App._voice_prewarm_failed(self,error)
 @Slot()
 def _voice_prewarm_finished(self):app.App._voice_prewarm_finished(self)

class OwnershipTests(unittest.TestCase):
 def setUp(self):
  self.qt=QApplication.instance() or QApplication([]);self.owner=Owner()
  p=patch.object(app,'WhisperTranscriptionWorker',ControlledWarmup);p.start();self.addCleanup(p.stop)
 def finish(self):
  worker=getattr(self.owner,'voice_prewarm_worker',None)
  if worker:worker.release.set()
  until=time.monotonic()+3
  while getattr(self.owner,'voice_prewarm_worker',None) is not None and time.monotonic()<until:QTest.qWait(10)
  self.assertIsNone(self.owner.voice_prewarm_worker)
 def test_gui_owned_warmup_coalesces_and_cleans_up(self):
  app.App.prewarm_whisper(self.owner);first=self.owner.voice_prewarm_worker
  try:
   app.App.prewarm_whisper(self.owner);self.assertIs(self.owner.voice_prewarm_worker,first);self.assertEqual(first.thread(),self.owner.thread());self.assertTrue(first.prewarm_only)
  finally:self.finish()
 def test_microphone_cancel_also_cancels_owned_warmup(self):
  app.App.prewarm_whisper(self.owner);worker=self.owner.voice_prewarm_worker
  try:
   app.App.cancel_voice_input(self.owner);self.assertTrue(worker.cancelled);self.assertFalse(self.owner.voice_recording);self.assertEqual(self.owner.voice_audio,b'')
  finally:self.finish()
 def test_warmup_error_is_reported_in_current_conversation(self):
  app.App.prewarm_whisper(self.owner);self.owner.voice_prewarm_worker.failed_message='controlled missing assets';self.finish()
  self.assertTrue(any(e.get('type')=='voiceError' and 'controlled missing assets' in e['message'] for e in self.owner.events))
 def test_old_conversation_warmup_error_is_ignored(self):
  app.App.prewarm_whisper(self.owner);self.owner.voice_prewarm_worker.failed_message='obsolete error';self.owner.current='chat-b';self.finish()
  self.assertFalse(any(e.get('type')=='voiceError' for e in self.owner.events))

if __name__=='__main__':unittest.main()
