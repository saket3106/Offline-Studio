"""Live Voice failures must leave capture disabled; no native speech inference."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import app

class ActivationTests(unittest.TestCase):
    def bridge(self):
        return SimpleNamespace(backend=SimpleNamespace(current='voice-test',busy=False,voice_mode_active=False,cancel_voice_input=Mock(),prewarm_whisper=Mock()),speech=Mock(),event=Mock(),_ensure_speech=Mock(),_cancel_pending_speech=Mock())

    def test_failed_warmup_rolls_back_voice_mode_and_capture(self):
        b=self.bridge();b.speech.warmup.side_effect=RuntimeError('speech setup failed')
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,True))
        self.assertFalse(result['ok']);self.assertFalse(b.backend.voice_mode_active)
        self.assertIn('speech setup failed',result['error'])
        b.backend.cancel_voice_input.assert_called_once_with()
        b._cancel_pending_speech.assert_called_once_with()
        states=[json.loads(c.args[0]) for c in b.event.emit.call_args_list]
        self.assertNotIn({'type':'liveVoiceMode','active':True},states)
        self.assertIn({'type':'liveVoiceMode','active':False},states)

    def test_exit_still_cancels_capture_if_playback_stop_raises(self):
        b=self.bridge();b.backend.voice_mode_active=True
        b.speech.stop.side_effect=RuntimeError('playback stop failed')
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,False))
        self.assertFalse(result['ok']);self.assertFalse(b.backend.voice_mode_active)
        b.backend.cancel_voice_input.assert_called_once_with()
        self.assertIn({'type':'liveVoiceMode','active':False},[json.loads(c.args[0]) for c in b.event.emit.call_args_list])

    def test_enable_acknowledges_only_after_preparation(self):
        b=self.bridge()
        b.speech.warmup.side_effect=lambda:self.assertFalse(b.backend.live_voice_session.capture_requested)
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,True))
        self.assertTrue(result['ok']);self.assertTrue(result['active'])
        self.assertEqual(result['session']['state'],'starting')
        self.assertFalse(result['session']['captureRequested'])
        self.assertTrue(b.backend.voice_mode_active)
        b.backend.prewarm_whisper.assert_called_once_with(make_room=True)  # Whisper first, chat model after
        self.assertTrue(b.backend.voice_chat_after_whisper)

    def test_repeated_enable_does_not_restart_preparation(self):
        b=self.bridge();app.DesktopBridge.setLiveVoiceMode(b,True);b._ensure_speech.reset_mock()
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,True))
        self.assertTrue(result['ok']);b._ensure_speech.assert_not_called()

    def test_cleanup_failure_does_not_hide_original_setup_failure(self):
        b=self.bridge();b._ensure_speech.side_effect=RuntimeError('original setup error')
        b.speech.stop.side_effect=RuntimeError('cleanup error')
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,True))
        self.assertFalse(result['ok']);self.assertIn('original setup error',result['error'])
        b.backend.cancel_voice_input.assert_called_once_with()
    def test_reported_async_controller_failure_cannot_be_acknowledged_as_enabled(self):
        b=self.bridge();b.speech.snapshot.return_value={'state':'error','error':'worker could not initialize'}
        result=json.loads(app.DesktopBridge.setLiveVoiceMode(b,True))
        self.assertFalse(result['ok']);self.assertFalse(b.backend.voice_mode_active)
        self.assertIn('worker could not initialize',result['error']);b.backend.prewarm_whisper.assert_not_called()
        b.backend.cancel_voice_input.assert_called_once_with()

if __name__=='__main__':unittest.main()
