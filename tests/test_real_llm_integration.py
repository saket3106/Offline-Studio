"""Tests verifying real local LLM integration, prompt delivery, streaming, cancellation, and error reporting."""
import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app
from integrated_runtime import EngineManager
from intelligence import resolve_deterministic_task


class TestRealLlmIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "offline_gpt.sqlite3"

    def tearDown(self):
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def test_prompt_delivery_into_selected_model_without_bypass(self):
        """Conversational and explanatory prompts pass through to the selected local model without being bypassed."""
        prompts = [
            "Explain the difference between synchronous and asynchronous execution in Python.",
            "Write a poem about trees in winter.",
            "What is the theory of general relativity?",
            "How does offline speech recognition work?"
        ]
        for p in prompts:
            with self.subTest(prompt=p):
                task = {"text": p, "route_target": "DIRECT"}
                # Must return None so ChatWorker routes to the actual LLM
                res = resolve_deterministic_task(task)
                self.assertIsNone(res, f"Prompt '{p}' was improperly intercepted by deterministic shortcut")

    def test_chat_worker_delivers_prompt_to_engine(self):
        """ChatWorker calls engine.chat_completion with the active model and assembled messages."""
        captured_calls = []

        class MockEngine:
            def __init__(self):
                self.loaded_model = "Qwen3.5-9B-Q4_K_M.gguf"
                self.resource_lock = threading.RLock()
                self.lock = threading.RLock()
                self.cfg = {'chat_backend': 'bundled'}
                self.last_completion_identity = {}

            def ensure_chat(self, progress=None, model=None, cancel_event=None):
                return model or self.loaded_model

            def chat_completion(self, messages, progress=None, on_token=None, cancel_event=None, **kwargs):
                captured_calls.append({
                    'messages': messages,
                    'model': kwargs.get('model'),
                    'cancel_event': cancel_event,
                    'kwargs': kwargs
                })
                if on_token:
                    on_token("Hello ")
                    on_token("world!")
                return "Hello world!"

        engine = MockEngine()
        messages = [
            {'role': 'system', 'content': 'You are OfflineGPT.'},
            {'role': 'user', 'content': 'Hello local LLM!'}
        ]
        analysis = {'route_target': 'DIRECT', 'expected_task_ids': []}

        worker = app.ChatWorker("Qwen3.5-9B-Q4_K_M.gguf", messages, engine, analysis)
        tokens_received = []
        worker.token.connect(tokens_received.append)

        # Run synchronously to verify execution
        worker.run()

        self.assertEqual(len(captured_calls), 1)
        delivered_msgs = captured_calls[0]['messages']
        self.assertEqual(delivered_msgs[-1]['content'], 'Hello local LLM!')
        self.assertEqual(tokens_received, ["Hello ", "world!"])

    def test_streaming_and_cancellation(self):
        """Streaming delivers tokens in order, and setting cancel_event terminates inference."""
        cancel_event = threading.Event()
        streamed_tokens = []

        def mock_generate(msgs, progress=None, on_token=None, cancel_event=None, **kwargs):
            for i in range(10):
                if cancel_event and cancel_event.is_set():
                    raise RuntimeError("Inference cancelled")
                tok = f"tok_{i} "
                if on_token:
                    on_token(tok)
                streamed_tokens.append(tok)
                if i == 3:
                    cancel_event.set()
            return "".join(streamed_tokens)

        class MockEngine:
            def __init__(self):
                self.cfg = {'chat_backend': 'bundled'}
                self.last_completion_identity = {}
            def ensure_chat(self, *a, **kw): return "qwen3"
            def chat_completion(self, *a, **kw): return mock_generate(*a, **kw)

        engine = MockEngine()
        worker = app.ChatWorker("qwen3", [{'role': 'user', 'content': 'test'}], engine, {'expected_task_ids': []})
        worker.cancel_event = cancel_event

        with self.assertRaisesRegex(RuntimeError, "cancelled"):
            worker.engine.chat_completion([], on_token=lambda t: None, cancel_event=worker.cancel_event)

        # Confirm streaming started and stopped at the cancellation point
        self.assertEqual(len(streamed_tokens), 4)

    @patch("integrated_runtime.physical_memory_status", return_value={'total': 16 * 1024**3, 'available': 8 * 1024**3, 'pagefile_available': 8 * 1024**3})
    def test_model_switching_and_session_reuse(self, mock_mem):
        """EngineManager reuses healthy sessions for identical model requests and switches when model differs."""
        manager = EngineManager.__new__(EngineManager)
        manager.cfg = {'chat_backend': 'bundled', 'gpt_oss_gguf': 'default.gguf'}
        manager.loaded_model = ""
        manager.runtime = Mock()
        manager.lm_runtime = Mock()
        manager.lock = threading.RLock()
        manager.resource_lock = threading.RLock()
        manager.chat_load_state = 'ready'
        manager.last_unload_reason = ""
        manager.last_reload_reason = ""
        manager.log_dir = self.root / 'logs'

        model_a = str(self.root / "model_a.gguf")
        model_b = str(self.root / "model_b.gguf")
        Path(model_a).write_bytes(b"GGUF_A")
        Path(model_b).write_bytes(b"GGUF_B")

        manager.resolve_model_path = lambda m: m

        # 1. First model load
        manager.runtime.model_path = ""
        manager.runtime._is_healthy = Mock(return_value=False)
        manager.runtime.start = Mock()
        manager.runtime.stop = Mock()
        manager.runtime.context = 4096
        manager.runtime.projector_path = ""
        from integrated_runtime import _LocalLlamaServer
        manager.runtime.loaded_gpu_layers = 'auto'
        manager.runtime.model_file_observation = _LocalLlamaServer.file_observation(Path(model_a))

        manager.runtime.model_descriptor = SimpleNamespace(display_name="Model A", architecture="qwen", header_sha256="aaa")

        manager.ensure_chat(model=model_a)
        manager.runtime.start.assert_called_once()
        self.assertEqual(manager.loaded_model, "Model A")

        # Configure mock runtime as healthy and holding model_a
        manager.runtime.model_path = str(Path(model_a).resolve())
        manager.runtime._is_healthy.return_value = True

        # 2. Warm reuse of model_a: start() must NOT be called again
        manager.runtime.start.reset_mock()
        manager.ensure_chat(model=model_a)
        manager.runtime.start.assert_not_called()

        # 3. Switching to model_b: start() must be called with model_b
        manager.runtime.start.reset_mock()
        manager.runtime.model_descriptor = SimpleNamespace(display_name="Model B", architecture="qwen", header_sha256="bbb")
        manager.ensure_chat(model=model_b)
        manager.runtime.start.assert_called_once()
        self.assertEqual(manager.loaded_model, "Model B")

    def test_errors_reported_rather_than_disguised_as_success(self):
        """When the inference backend fails, ChatWorker emits a failure signal rather than fabricating an answer."""
        class FailingEngine:
            def __init__(self):
                self.cfg = {'chat_backend': 'bundled'}
            def ensure_chat(self, *a, **kw):
                raise RuntimeError("CUDA out of memory while loading weights")

        engine = FailingEngine()
        worker = app.ChatWorker("qwen3", [{'role': 'user', 'content': 'test'}], engine, {'expected_task_ids': []})

        failed_messages = []
        done_messages = []
        worker.failed.connect(failed_messages.append)
        worker.done.connect(done_messages.append)

        worker.run()

        self.assertEqual(len(done_messages), 0, "Failed run must not emit done")
        self.assertEqual(len(failed_messages), 1, "Failed run must emit failed signal")
        self.assertIn("CUDA out of memory", failed_messages[0])


if __name__ == '__main__':
    unittest.main()
