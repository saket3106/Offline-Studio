"""Live Voice loads Whisper on the GPU first and fits the chat model around it.

Measured 2026-11-07 on an 8 GB RTX 4060: loading the 9B chat model first left 0.75-1.25 GB free, so
Whisper ran on the CPU (10-12 s per spoken turn); a later turn then unloaded the chat model for low RAM
and the answer waited for a full model reload. With Whisper warm on the GPU, a turn takes ~0.4 s.
"""
import os, sys, threading, unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app


class FakeProcess:
    def __init__(self, alive=True): self.alive = alive
    def poll(self): return None if self.alive else 0


class WarmStateTests(unittest.TestCase):
    def setUp(self):
        self.saved = {k: app._WARM_WHISPER.get(k) for k in ('process', 'key', 'timer')}

    def tearDown(self):
        timer = app._WARM_WHISPER.get('timer')
        if timer and timer is not self.saved['timer']: timer.cancel()
        app._WARM_WHISPER.update(self.saved)

    def test_backend_of_live_warm_server(self):
        app._WARM_WHISPER.update(process=FakeProcess(), key=('server', 'model', 4, 'cuda'), timer=None)
        self.assertEqual(app.warm_whisper_backend(), 'cuda')
        app._WARM_WHISPER['process'] = FakeProcess(alive=False)
        self.assertIsNone(app.warm_whisper_backend())
        app._WARM_WHISPER.update(process=None, key=None)
        self.assertIsNone(app.warm_whisper_backend())

    def test_idle_stop_is_scheduled_only_for_a_live_server(self):
        app._WARM_WHISPER.update(process=None, key=None, timer=None)
        self.assertFalse(app.schedule_warm_whisper_stop(60))
        app._WARM_WHISPER.update(process=FakeProcess(), key=('s', 'm', 4, 'cuda'), timer=None)
        self.assertTrue(app.schedule_warm_whisper_stop(60))
        timer = app._WARM_WHISPER['timer']
        self.assertIsInstance(timer, threading.Timer); self.assertTrue(timer.is_alive())
        timer.cancel()


class ReleaseTests(unittest.TestCase):
    def release(self, purpose, voice=True, backend='cuda'):
        owner = SimpleNamespace(voice_mode_active=voice, _whisper_rewarm=False)
        with patch.object(app, 'warm_whisper_backend', return_value=backend), patch.object(app, 'stop_warm_whisper') as stop:
            app.App._release_whisper_for_model(owner, purpose=purpose)
        return stop.called, owner._whisper_rewarm

    def test_gpu_whisper_survives_chat_and_speech_loads_in_voice(self):
        self.assertEqual(self.release('chat'), (False, False))
        self.assertEqual(self.release('speech'), (False, False))

    def test_other_cases_still_release_whisper(self):
        self.assertEqual(self.release('', voice=True), (True, True), 'image/vision jobs still free the GPU')
        self.assertEqual(self.release('chat', voice=False), (True, False), 'outside voice nothing is kept')
        self.assertEqual(self.release('chat', backend='cpu'), (True, True), 'a CPU Whisper is replaced after the load')


class ChatAfterWhisperTests(unittest.TestCase):
    def finish(self, voice=True, flag=True, unloaded=False):
        worker = SimpleNamespace(unloaded_chat=unloaded, deleteLater=Mock())
        owner = SimpleNamespace(voice_mode_active=voice, voice_chat_after_whisper=flag, voice_prewarm_worker=worker,
                                preload_voice_chat=Mock(), sender=lambda: worker)
        app.App._voice_prewarm_finished(owner)
        return owner

    def test_chat_model_loads_after_whisper_is_warm(self):
        owner = self.finish()
        owner.preload_voice_chat.assert_called_once_with()
        self.assertFalse(owner.voice_chat_after_whisper); self.assertIsNone(owner.voice_prewarm_worker)

    def test_chat_unloaded_to_make_room_is_reloaded(self):
        self.finish(flag=False, unloaded=True).preload_voice_chat.assert_called_once_with()

    def test_no_chat_load_after_voice_ended_or_plain_prewarm(self):
        self.finish(voice=False).preload_voice_chat.assert_not_called()
        self.finish(flag=False).preload_voice_chat.assert_not_called()

    def test_preload_skips_a_ready_model(self):
        engines = SimpleNamespace(ensure_chat=Mock(), runtime=SimpleNamespace(ready=True))
        self.assertFalse(app.App.preload_voice_chat(SimpleNamespace(engines=engines)))
        engines.runtime.ready = False
        self.assertTrue(app.App.preload_voice_chat(SimpleNamespace(engines=engines)))
        for thread in threading.enumerate():
            if thread.name == 'voice-chat-preload': thread.join(5)
        engines.ensure_chat.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
