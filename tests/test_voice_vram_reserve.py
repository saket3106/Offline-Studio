"""Live Voice reserves GPU memory for Whisper.

Measured on the user's RTX 4060 (8 GB): with llama.cpp's 512 MiB fit target the 9B chat model left
300-460 MiB free, Whisper fell back to the CPU and every spoken turn took ~12.5 s to transcribe.
"""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import Mock, patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model_runtime import ModelBehavior, GIB
from integrated_runtime import _LocalLlamaServer, chat_fit_target_mb, VOICE_VRAM_RESERVE_MB
from tests.test_model_runtime import info
import app


class FitTargetTests(unittest.TestCase):
    def test_reserve_adds_to_base_margin(self):
        self.assertEqual(chat_fit_target_mb(False, 0), 512)
        self.assertEqual(chat_fit_target_mb(True, 0), 1024)
        self.assertEqual(chat_fit_target_mb(False, VOICE_VRAM_RESERVE_MB), 512 + VOICE_VRAM_RESERVE_MB)
        self.assertEqual(chat_fit_target_mb(False, None), 512)
        self.assertEqual(chat_fit_target_mb(False, -5), 512)

    def test_reserve_covers_whisper_gpu_threshold(self):
        # After the load the free VRAM must still pass Whisper's own GPU check.
        free_after_load = chat_fit_target_mb(False, VOICE_VRAM_RESERVE_MB) * 1024**2
        self.assertEqual(app.select_whisper_backend('auto', free_after_load)[0], 'cuda')


class LauncherTests(unittest.TestCase):
    def launch(self, runtime, model):
        def bind(_):
            runtime.model_descriptor = info('qwen3'); runtime.behavior = ModelBehavior.from_model(runtime.model_descriptor)
        process = Mock(); process.poll.return_value = None
        response = Mock(); response.__enter__ = Mock(return_value=response); response.__exit__ = Mock(return_value=False); response.status = 200
        with patch.object(runtime, 'inspect_behavior', side_effect=bind), patch.object(runtime, 'stop'), \
             patch.object(runtime, '_server_binary', return_value=model.parent / 'llama-server.exe'), patch.object(runtime, '_check_runtime_files'), \
             patch('integrated_runtime.subprocess.Popen', return_value=process) as popen, patch.object(runtime._local_opener, 'open', return_value=response), \
             patch('integrated_runtime.physical_memory_status', return_value={'available': 4 * GIB}), patch.object(runtime, '_is_healthy', return_value=True):
            try: runtime.start(model, 2048, 'auto', lambda _: None, memory_profile={'batch': 32})
            finally:
                if runtime.log_handle: runtime.log_handle.close()
        return popen

    def test_fit_target_follows_reserve_and_a_smaller_load_is_replaced(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'model.gguf'; model.write_bytes(b'fixture')
            runtime = _LocalLlamaServer(Path(folder))
            args = self.launch(runtime, model).call_args.args[0]
            self.assertEqual(args[args.index('--fit-target') + 1], '512')
            self.assertEqual(runtime.loaded_fit_target, 512)
            runtime.vram_reserve_mb = VOICE_VRAM_RESERVE_MB
            popen = self.launch(runtime, model)
            self.assertTrue(popen.called, 'a load without room for Whisper is reloaded')
            args = popen.call_args.args[0]
            self.assertEqual(args[args.index('--fit-target') + 1], str(512 + VOICE_VRAM_RESERVE_MB))

    def test_leaving_voice_does_not_force_a_reload(self):
        with tempfile.TemporaryDirectory() as folder:
            model = Path(folder) / 'model.gguf'; model.write_bytes(b'fixture')
            runtime = _LocalLlamaServer(Path(folder)); runtime.vram_reserve_mb = VOICE_VRAM_RESERVE_MB
            self.launch(runtime, model)
            runtime.vram_reserve_mb = 0
            self.assertFalse(self.launch(runtime, model).called, 'a load with extra room is kept')


if __name__ == '__main__':
    unittest.main()
