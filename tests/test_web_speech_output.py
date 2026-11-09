import os, sys, tempfile, unittest
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaPlayer
import voice_runtime


class WebSpeechOutputTests(unittest.TestCase):
    """Spoken answers play in the web UI (echo-cancelled) with Qt fallback."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.sent = []; voice_runtime.WEB_AUDIO_SINK = self.sent.append
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.addCleanup(self.tmp.cleanup)
        self.wav = Path(self.tmp.name) / 'chunk.wav'; self.wav.write_bytes(b'RIFF0000WAVE')
        controller = voice_runtime.make_controller(None, self.tmp.name, {'speech_engine': 'sapi'}, lambda cfg: None, cache_dir=self.tmp.name)
        self.player = controller.player; self.states = []; self.statuses = []
        self.player.playbackStateChanged.connect(self.states.append); self.player.mediaStatusChanged.connect(self.statuses.append)

    def tearDown(self):
        voice_runtime.WEB_AUDIO_SINK = None

    def test_chunk_goes_to_web_and_end_is_reported_like_qt(self):
        self.player.setSource(QUrl.fromLocalFile(str(self.wav))); self.player.play()
        self.assertEqual(self.sent[-1]['op'], 'play'); self.assertEqual(self.player.route, 'web')
        seq = self.sent[-1]['seq']
        self.assertTrue(self.player.on_web(seq, 'started'))
        self.assertEqual(self.states[-1], QMediaPlayer.PlaybackState.PlayingState)
        self.player.on_web(seq, 'ended')
        self.assertEqual(self.statuses[-1], QMediaPlayer.MediaStatus.EndOfMedia)
        self.assertEqual(self.states[-1], QMediaPlayer.PlaybackState.StoppedState)

    def test_stop_tells_web_and_ignores_late_events(self):
        self.player.setSource(QUrl.fromLocalFile(str(self.wav))); self.player.play(); seq = self.sent[-1]['seq']
        self.player.on_web(seq, 'started'); self.player.stop()
        self.assertEqual(self.sent[-1]['op'], 'stop')
        self.assertFalse(self.player.on_web(seq, 'ended'))  # stale chunk cannot advance the queue
        self.assertNotIn(QMediaPlayer.MediaStatus.EndOfMedia, self.statuses)

    def test_error_or_timeout_falls_back_to_qt(self):
        self.player.setSource(QUrl.fromLocalFile(str(self.wav))); self.player.play(); seq = self.sent[-1]['seq']
        self.player.on_web(seq, 'error'); self.assertEqual(self.player.route, 'qt')
        self.player.play(); self.player._web_timeout(); self.assertEqual(self.player.route, 'qt')

    def test_no_sink_uses_qt(self):
        voice_runtime.WEB_AUDIO_SINK = None
        self.player.setSource(QUrl.fromLocalFile(str(self.wav))); self.player.play()
        self.assertEqual(self.player.route, 'qt'); self.assertEqual(self.sent, [])


if __name__ == '__main__':
    unittest.main()
