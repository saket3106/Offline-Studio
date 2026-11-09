import os, sys, unittest
from unittest.mock import Mock, patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import app
from app import _WARM_WHISPER, reuse_warm_cuda_whisper, whisper_cpu_threads


class WarmWhisperReuseTests(unittest.TestCase):
    """Live voice: a warm CUDA Whisper must not be replaced by CPU because its own VRAM
    is missing from the free-VRAM measurement (measured 21 s CPU vs 0.35 s CUDA)."""

    def setUp(self):
        self.saved = dict(_WARM_WHISPER)

    def tearDown(self):
        _WARM_WHISPER.clear(); _WARM_WHISPER.update(self.saved)

    def warm(self, backend='cuda', alive=True, threads=4):
        process = Mock(); process.poll.return_value = None if alive else 0
        _WARM_WHISPER.update(process=process, key=('srv', 'model', threads, backend))

    def test_reuses_live_cuda_process(self):
        self.warm()
        self.assertEqual(reuse_warm_cuda_whisper('srv', 'model', 'auto'), ('cuda', 'warm_cuda_reuse', 4))

    def test_selection_with_low_measured_vram_alone_would_pick_cpu(self):
        self.assertEqual(app.select_whisper_backend('auto', 700 * 1024**2)[0], 'cpu')

    def test_no_reuse_for_cpu_dead_or_other_model_or_explicit_cpu(self):
        self.warm(backend='cpu'); self.assertEqual(reuse_warm_cuda_whisper('srv', 'model', 'auto')[0], None)
        self.warm(alive=False); self.assertEqual(reuse_warm_cuda_whisper('srv', 'model', 'auto')[0], None)
        self.warm(); self.assertEqual(reuse_warm_cuda_whisper('srv', 'other', 'auto')[0], None)
        self.warm(); self.assertEqual(reuse_warm_cuda_whisper('srv', 'model', 'cpu')[0], None)

    def test_cpu_fallback_uses_more_threads_but_respects_higher_config(self):
        with patch('app.os.cpu_count', return_value=24):
            self.assertEqual(whisper_cpu_threads(4), 12)
            self.assertEqual(whisper_cpu_threads(16), 16)
        with patch('app.os.cpu_count', return_value=4):
            self.assertEqual(whisper_cpu_threads(4), 4)


if __name__ == '__main__':
    unittest.main()
