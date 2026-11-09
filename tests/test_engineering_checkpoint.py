import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tools.engineering_checkpoint import identities, recover, save, select_fallback, source_path
from tools.probe_engineering_routes import probe, request, save_results


class CheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / 'Source'
        self.source.mkdir()
        (self.source / 'unit.py').write_text('before', encoding='utf-8')
        self.path = self.root / 'checkpoint.json'
        self.state = dict(schema_version=1, objective='Repair agent', backlog=['repair'],
                          completed=[], pending=['repair'], ownership={}, source_root=str(self.source),
                          source_revision='revision', files=identities(self.source, ['unit.py']),
                          tests=[], blockers=[], routes=[], dependencies=[], next_action='Review', usage={})
        self.git = patch('tools.engineering_checkpoint.subprocess.run',
                         return_value=SimpleNamespace(returncode=0, stdout='revision\n'))
        self.git.start()
        self.addCleanup(self.git.stop)

    def test_saved_checkpoint_roundtrip(self):
        saved = save(self.path, self.state, 0)
        self.assertEqual(saved['revision'], 1)
        self.assertEqual(recover(self.path, self.source)['status'], 'READY')
        self.assertFalse(self.path.with_suffix('.json.lock').exists())

    def test_stale_writer_cannot_replace_newer_state(self):
        save(self.path, self.state, 0)
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'changed'):
            save(self.path, self.state, 0)
        self.assertEqual(self.path.read_bytes(), before)

    def test_failed_atomic_replace_preserves_previous_checkpoint(self):
        save(self.path, self.state, 0)
        before = self.path.read_bytes()
        with patch('tools.engineering_checkpoint.os.replace', side_effect=OSError('interrupted')):
            with self.assertRaises(OSError):
                save(self.path, self.state, 1)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_live_or_stale_lock_is_never_stolen(self):
        lock = self.path.with_suffix('.json.lock')
        lock.write_text('unknown owner')
        with self.assertRaises(FileExistsError):
            save(self.path, self.state, 0)
        self.assertEqual(lock.read_text(), 'unknown owner')

    def test_interrupted_task_detects_changed_files_without_replaying(self):
        self.state['ownership'] = {'unit.py': 'interrupted-worker'}
        save(self.path, self.state, 0)
        (self.source / 'unit.py').write_text('partially applied', encoding='utf-8')
        result = recover(self.path, self.source)
        self.assertEqual(result['status'], 'REVIEW_REQUIRED')
        self.assertEqual(result['changed_files'], ['unit.py'])
        self.assertEqual(result['actions_executed'], 0)
        self.assertEqual((self.source / 'unit.py').read_text(), 'partially applied')

    def test_missing_and_new_files_are_detected(self):
        self.state['files'] = identities(self.source, ['unit.py', 'new.py'])
        save(self.path, self.state, 0)
        (self.source / 'unit.py').unlink()
        (self.source / 'new.py').write_text('new')
        self.assertEqual(set(recover(self.path, self.source)['changed_files']), {'unit.py', 'new.py'})

    def test_changed_git_revision_requires_review(self):
        self.state['source_revision'] = 'previous'
        save(self.path, self.state, 0)
        self.assertEqual(recover(self.path, self.source)['status'], 'REVIEW_REQUIRED')

    def test_wrong_root_rejected(self):
        save(self.path, self.state, 0)
        with self.assertRaisesRegex(ValueError, 'another source'):
            recover(self.path, self.root)

    def test_path_escape_rejected(self):
        for relative in ('../outside.py', str(self.root / 'outside.py'), '.'):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                source_path(self.source, relative)

    def test_owned_paths_require_hashes(self):
        self.state['ownership'] = {'untracked.py': 'worker'}
        with self.assertRaisesRegex(ValueError, 'identities'):
            save(self.path, self.state, 0)

    def test_fallback_is_bounded_authorized_and_capability_matched(self):
        routes = [dict(id='bad', status='unavailable', authorized=True, capabilities=['coding']),
                  dict(id='synthetic', status='verified', authorized=True, capabilities=['synthetic']),
                  dict(id='unauthorized', status='verified', authorized=False, capabilities=['coding']),
                  dict(id='worker', status='verified', authorized=True, capabilities=['coding'])]
        self.assertEqual(select_fallback(routes, ['primary'], 'coding'), 'worker')
        self.assertIsNone(select_fallback(routes, ['primary', 'worker'], 'coding'))
        self.assertIsNone(select_fallback(routes, ['worker'], 'coding'))


class RouteProbeTests(unittest.TestCase):
    def test_requires_real_tool_output_nonce(self):
        def respond(payload, timeout):
            if len(payload['input']) == 1:
                return {'output': [{'type': 'function_call', 'name': 'read_probe',
                                    'arguments': '{}', 'call_id': 'call'}]}
            value = json.loads(payload['input'][-1]['output'])['value']
            return {'status': 'completed', 'output': [{'content': [{'type': 'output_text', 'text': value}]}]}
        with patch('tools.probe_engineering_routes.request', side_effect=respond):
            result = probe('synthetic-test')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['requests'], 2)
        self.assertNotIn('coding', result['capabilities'])

    def test_plain_text_is_not_tool_support(self):
        with patch('tools.probe_engineering_routes.request', return_value={'output': []}):
            self.assertEqual(probe('test')['status'], 'tool_contract_failed')

    def test_error_messages_cannot_leak_secrets(self):
        with patch('tools.probe_engineering_routes.request', side_effect=RuntimeError('SECRET')):
            result = probe('test')
        self.assertEqual(result['status'], 'unavailable')
        self.assertNotIn('SECRET', json.dumps(result))

    def test_transport_is_direct_loopback_and_never_follows_redirect(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 302
        with patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'synthetic-key', 'HTTP_PROXY': 'http://external.invalid'}), \
                patch('tools.probe_engineering_routes.http.client.HTTPConnection', return_value=connection) as factory:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                request({'model': 'synthetic'}, 2)
        self.assertEqual(caught.exception.code, 302)
        factory.assert_called_once_with('127.0.0.1', 20128, timeout=2)
        self.assertEqual(connection.request.call_count, 1)
        connection.close.assert_called_once()

    def test_response_size_is_bounded(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read1.return_value = b'x' * 17
        with patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'synthetic-key'}), \
                patch('tools.probe_engineering_routes.MAX_RESPONSE_BYTES', 16), \
                patch('tools.probe_engineering_routes.http.client.HTTPConnection', return_value=connection):
            with self.assertRaisesRegex(ValueError, 'size limit'):
                request({}, 2)
        connection.close.assert_called_once()

    def test_absolute_deadline_stops_trickling_response(self):
        connection = MagicMock()
        connection.getresponse.return_value.status = 200
        connection.getresponse.return_value.read1.return_value = b' '
        with patch.dict(os.environ, {'OMNIROUTE_API_KEY': 'synthetic-key'}), \
                patch('tools.probe_engineering_routes.http.client.HTTPConnection', return_value=connection), \
                patch('tools.probe_engineering_routes.threading.Timer'), \
                patch('tools.probe_engineering_routes.time.monotonic', side_effect=[0, 0, 1, 3]):
            with self.assertRaises(TimeoutError):
                request({}, 2)
        self.assertEqual(connection.getresponse.return_value.read1.call_count, 1)

    def test_probe_receipts_survive_failed_replace(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'receipt.json'
            save_results(path, [{'status': 'verified'}])
            before = path.read_bytes()
            with patch('tools.probe_engineering_routes.os.replace', side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):
                    save_results(path, [])
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(path.parent.glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
