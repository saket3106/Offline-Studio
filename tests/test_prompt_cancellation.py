"""Real loopback transport and cancellation; no native model or user profile."""
import json
import threading
import time
import unittest
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from integrated_runtime import _LocalLlamaServer
from model_runtime import EngineTextRuntime
from agent_runtime import LocalAgentModel


class PromptCancellationTests(unittest.TestCase):
    def setUp(self):
        self.entered = threading.Event()
        self.release = threading.Event()
        self.records = []
        self.delay_path = '/apply-template'
        self.partial_body = False
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                fixture.records.append((self.path, payload))
                data = json.dumps({'prompt': 'exact template'} if self.path == '/apply-template'
                                  else {'tokens': [7, 11, 13, 17]}).encode()
                delayed = self.path == fixture.delay_path
                if delayed and not fixture.partial_body:
                    fixture.entered.set(); fixture.release.wait(2)
                self.send_response(302 if self.path == '/redirect' else 200)
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Location', '/must-not-follow')
                self.end_headers()
                try:
                    if delayed and fixture.partial_body:
                        self.wfile.write(data[:2]); self.wfile.flush()
                        fixture.entered.set(); fixture.release.wait(2)
                        self.wfile.write(data[2:])
                    else: self.wfile.write(data)
                except OSError: pass  # The client deliberately shuts its socket.

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        self.runtime = _LocalLlamaServer(Path.cwd())
        self.runtime.port = self.server.server_port

    def tearDown(self):
        self.release.set()
        self.server.shutdown(); self.server.server_close(); self.thread.join(2)
        self.assertFalse(self.thread.is_alive())
        self.assertFalse(any(t.name == 'OfflineGPT-prompt-request' for t in threading.enumerate()))

    def cancel_request(self, function):
        cancel = threading.Event(); outcome = {}
        def run():
            try: outcome['result'] = function(cancel)
            except Exception as exc: outcome['error'] = str(exc)
        worker = threading.Thread(target=run); worker.start()
        self.assertTrue(self.entered.wait(2))
        start = time.perf_counter(); cancel.set(); worker.join(1)
        latency = (time.perf_counter() - start) * 1000
        self.assertFalse(worker.is_alive(), 'Cancellation left a request worker alive')
        self.assertEqual(outcome, {'error': 'Cancelled'})
        self.assertLess(latency, 500)
        return latency

    def test_cancel_during_template_headers_stops_before_tokenize(self):
        latency = self.cancel_request(lambda cancel: self.runtime._prompt_tokens([], cancel_event=cancel))
        self.assertEqual([p for p, _ in self.records], ['/apply-template'])
        print(f'PROMPT_CANCEL_HEADERS_MS={latency:.2f}')

    def test_cancel_during_token_body_does_not_return_stale_count(self):
        self.delay_path = '/tokenize'; self.partial_body = True
        latency = self.cancel_request(lambda cancel: self.runtime._prompt_tokens([], cancel_event=cancel))
        self.assertEqual([p for p, _ in self.records], ['/apply-template', '/tokenize'])
        print(f'PROMPT_CANCEL_BODY_MS={latency:.2f}')

    def test_precancelled_request_never_contacts_server(self):
        cancel = threading.Event(); cancel.set()
        with self.assertRaisesRegex(RuntimeError, '^Cancelled$'):
            self.runtime._prompt_tokens([], cancel_event=cancel)
        self.assertEqual(self.records, [])

    def test_deadline_bounds_slow_headers_without_cancel(self):
        start = time.perf_counter()
        with self.assertRaises(RuntimeError):
            self.runtime._json_request('/apply-template', {}, timeout=.12)
        self.assertLess(time.perf_counter() - start, .6)

    def test_cancel_one_request_leaves_independent_request_usable(self):
        self.cancel_request(lambda cancel: self.runtime._prompt_tokens([], cancel_event=cancel))
        self.release.set()
        self.assertEqual(self.runtime._prompt_tokens([{'role': 'user', 'content': 'independent'}]), 4)
        self.assertEqual(self.records[-1][1], {'content': 'exact template', 'add_special': False, 'parse_special': True})

    def test_redirect_is_an_error_and_never_followed(self):
        with self.assertRaisesRegex(RuntimeError, '302'):
            self.runtime._json_request('/redirect', {})
        self.assertEqual([p for p, _ in self.records], ['/redirect'])

    def test_real_facade_agent_cancel_never_generates_or_charges_unknown_tokens(self):
        self.runtime.ready_marker = True
        engine = SimpleNamespace(cfg={'chat_backend': 'bundled'}, runtime=self.runtime,
                                 resource_lease=lambda _: nullcontext(), last_completion_identity={},
                                 ensure_chat=Mock(), chat_completion=Mock())
        # Only readiness/load are substituted. Counting uses the real facade,
        # planner and HTTP transport, with a genuinely delayed socket.
        engine.text_runtime = EngineTextRuntime(engine)
        from unittest.mock import patch
        with patch.object(type(self.runtime), 'ready', new_callable=lambda: property(lambda _: True)):
            model = LocalAgentModel(engine)
            self.cancel_request(lambda cancel: model([], cancel, time.monotonic()+5))
        engine.chat_completion.assert_not_called()
        self.assertEqual(model.total_tokens, 0)


if __name__ == '__main__': unittest.main()
