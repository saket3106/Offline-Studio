"""Bounded source regressions for document recovery identity; no model inference."""
import asyncio
import json
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest

import pymupdf

from agent_mcp import WorkspaceTools
from agent_permissions import GrantAuthority
from agent_resources import AgentSpecialists, AttachmentRegistry
from agent_runtime import AgentRuntime, is_same_objective_recovered
from agent_workspace import WorkspaceAccess


class RecoveryIdentityTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='agent-recovery-20261030-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'workspace'
        self.root.mkdir()
        self.access = WorkspaceAccess(self.root)
        self.addCleanup(self.access.close)
        self.tools = WorkspaceTools(self.access, GrantAuthority(b'r' * 32))
        self.attachments = AttachmentRegistry()

    def make_pdf(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with pymupdf.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), 'Verified text from the available report.')
            document.save(path)

    def run_plans(self, plans, prompt):
        tools = self.tools
        calls = []

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def call(self, tool, args, approved=False):
                calls.append((tool, dict(args)))
                return tools.call(tool, args)

        responses = iter(plans)
        events = []
        runtime = AgentRuntime(
            lambda *_: json.dumps(next(responses)), self.root, None,
            'recovery-fixture', events.append,
            client_factory=lambda *_, **__: Client(),
        )
        runtime.resources = self.attachments.public()
        runtime.specialists = AgentSpecialists(
            SimpleNamespace(), self.access, self.attachments,
        )
        asyncio.run(runtime.run(prompt))
        self.assertEqual(len(runtime.traces), 2)
        self.assertEqual([trace['status'] for trace in runtime.traces], ['error', 'completed'])
        self.assertTrue(runtime.traces[1]['output']['coverage_complete'])
        self.assertEqual(events[-1]['state'], runtime.state)
        return runtime, calls

    def test_same_basename_in_another_directory_does_not_complete_failed_read(self):
        (self.root / 'a').mkdir()
        self.make_pdf(self.root / 'b' / 'report.pdf')
        runtime, calls = self.run_plans([
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'a/report.pdf', 'page': '1'}},
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'b/report.pdf', 'page': '1'}},
            {'final': 'Both reports have been read.'},
        ], 'Read a/report.pdf and b/report.pdf.')
        self.assertEqual(runtime.state, 'PARTIAL', runtime.final)
        self.assertIn('a/report.pdf', runtime.final)
        self.assertEqual([args['path'] for _, args in calls], ['a/report.pdf', 'b/report.pdf'])

    def test_attachment_basename_does_not_replace_explicit_workspace_directory(self):
        (self.root / 'a').mkdir()
        attachment = self.root.parent / 'report.pdf'
        self.make_pdf(attachment)
        record = self.attachments.register([str(attachment)], 'recovery-fixture')[0]
        runtime, _ = self.run_plans([
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'a/report.pdf', 'page': '1'}},
            {'tool': 'read_attachment', 'arguments': {'source': record['id'], 'page': '1'}},
            {'final': 'Both reports have been read.'},
        ], 'Read a/report.pdf and the attached report.pdf.')
        self.assertEqual(runtime.state, 'PARTIAL', runtime.final)
        self.assertIn('a/report.pdf', runtime.final)

    def test_unqualified_attachment_filename_recovery_still_completes(self):
        attachment = self.root.parent / 'report.pdf'
        self.make_pdf(attachment)
        record = self.attachments.register([str(attachment)], 'recovery-fixture')[0]
        runtime, _ = self.run_plans([
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'report.pdf', 'page': '1'}},
            {'tool': 'read_attachment', 'arguments': {'source': record['id'], 'page': '1'}},
            {'final': 'The report says: Verified text from the available report.'},
        ], 'Read report.pdf.')
        self.assertEqual(runtime.state, 'COMPLETED', runtime.final)

    def test_exact_attachment_id_retry_recovers_failed_attachment_read(self):
        attachment = self.root.parent / 'report.pdf'
        self.make_pdf(attachment)
        record = self.attachments.register([str(attachment)], 'recovery-fixture')[0]
        failed = {'tool': 'read_attachment', 'args': {'source': record['id'], 'page': '1'},
                  'result': {'error': 'Temporary read failure'}}
        successful = {'tool': 'read_attachment', 'args': {'source': record['id'], 'page': '1'},
                      'result': {'source': record['id'], 'name': record['name'], 'coverage_complete': True}}
        self.assertTrue(is_same_objective_recovered(failed, [successful], self.attachments.public()))

    def test_same_tool_recovery_requires_full_path_and_read_scope(self):
        for tool, scope in (
            ('extract_pdf_text', {'page': '1'}),
            ('read_docx', {}),
            ('read_local_file', {'start_line': '1', 'line_count': '10'}),
        ):
            failed = {'tool': tool, 'args': dict(path='a/report', **scope),
                      'result': {'error': 'Temporary read failure'}}
            for path, expected in (('a/report', True), ('b/report', False), ('report', False)):
                success = {'tool': tool, 'args': dict(path=path, **scope),
                           'result': {'coverage_complete': True}}
                with self.subTest(tool=tool, path=path):
                    self.assertEqual(is_same_objective_recovered(failed, [success], []), expected)
            if scope:
                changed_scope = dict(scope)
                changed_scope[next(iter(scope))] = '2'
                success = {'tool': tool, 'args': dict(path='a/report', **changed_scope),
                           'result': {'coverage_complete': True}}
                with self.subTest(tool=tool, changed_scope=changed_scope):
                    self.assertFalse(is_same_objective_recovered(failed, [success], []))

    def test_permission_cancellation_and_incomplete_evidence_still_fail_closed(self):
        failed = {'tool': 'extract_pdf_text', 'args': {'path': 'a/report.pdf', 'page': '1'},
                  'result': {'error': 'Temporary read failure'}}
        success = {'tool': 'extract_pdf_text', 'args': dict(failed['args']),
                   'result': {'coverage_complete': True}}
        denied = dict(failed, result={'error': 'Permission denied'})
        self.assertFalse(is_same_objective_recovered(denied, [success], []))
        cancelled = threading.Event()
        cancelled.set()
        self.assertFalse(is_same_objective_recovered(failed, [success], [], cancelled))
        for restriction in ({'error': 'Read failed'}, {'omitted': True}, {'truncated': True},
                            {'coverage_complete': False}, {'scannedPagesRequiringOcr': [1]}):
            with self.subTest(restriction=restriction):
                incomplete = dict(success, result=dict(success['result'], **restriction))
                self.assertFalse(is_same_objective_recovered(failed, [incomplete], []))


if __name__ == '__main__':
    unittest.main()
