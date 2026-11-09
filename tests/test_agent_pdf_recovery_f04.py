"""Regression suite for F04 / R01: PDF attachment routing, recovery semantics, and boundary guards."""
import asyncio
import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pymupdf
from PIL import Image

from agent_mcp import WorkspaceTools, ToolContractError
from agent_permissions import GrantAuthority
from agent_resources import AttachmentRegistry, AgentSpecialists, document_evidence
from agent_runtime import AgentRuntime, request_tool_policy, is_same_objective_recovered
from agent_workspace import WorkspaceAccess


class LocalClient:
    """Mock MCP client that routes workspace tool calls to WorkspaceTools."""
    def __init__(self, tools):
        self.tools = tools
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        pass

    async def call(self, tool, args, approved=False):
        self.calls.append((tool, args))
        return self.tools.call(tool, args)


class AgentPdfRecoveryF04Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.temp_root = Path(self.temp.name)

        # Separate outside attachment directory from workspace sandbox
        self.outside_dir = self.temp_root / 'outside'
        self.outside_dir.mkdir()
        self.workspace_dir = self.temp_root / 'workspace'
        self.workspace_dir.mkdir()

        self.access = WorkspaceAccess(self.workspace_dir)
        self.addCleanup(self.access.close)
        self.authority = GrantAuthority(b'k' * 32)
        self.tools = WorkspaceTools(self.access, self.authority)

        self.registry = AttachmentRegistry()
        self.specialists = AgentSpecialists(
            SimpleNamespace(vision_model_status=lambda: {'visionAvailable': False, 'visionMessage': 'No vision model'}),
            self.access,
            self.registry
        )

    def _create_pdf(self, path: Path, pages: list[str]) -> Path:
        doc = pymupdf.open()
        for text in pages:
            page = doc.new_page()
            page.insert_text((72, 72), text)
        doc.save(path)
        doc.close()
        return path

    def _make_task(self, plans: list[dict], prompt: str) -> AgentRuntime:
        it = iter(plans)
        client = LocalClient(self.tools)
        task = AgentRuntime(
            lambda *_: json.dumps(next(it)),
            self.workspace_dir,
            None,
            'chat-f04',
            lambda _: None,
            client_factory=lambda *_, **__: client
        )
        task.resources = self.registry.public()
        task.specialists = self.specialists
        asyncio.run(task.run(prompt))
        return task

    def test_end_to_end_pdf_recovery_after_failed_extraction(self):
        """Initial failed extract_pdf_text followed by successful read_attachment completes with honest trace."""
        pdf_file = self.outside_dir / 'physical-pages.pdf'
        self._create_pdf(pdf_file, ['Page 1 Introduction', 'Page 2 Canary: CANARY-482-VERIFIED'])
        record = self.registry.register([str(pdf_file)], 'chat-f04')[0]

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'physical-pages.pdf', 'page': '2'}},
            {'tool': 'read_attachment', 'arguments': {'source': record['id'], 'page': '2'}},
            {'final': 'The canary on physical page 2 of physical-pages.pdf is CANARY-482-VERIFIED.'}
        ]

        task = self._make_task(plans, 'What is the canary on physical page 2 of physical-pages.pdf?')
        self.assertEqual(task.state, 'COMPLETED')
        self.assertIn('CANARY-482-VERIFIED', task.final)
        self.assertNotIn('Task is partial', task.final)
        self.assertNotIn('Actual tool limitations', task.final)

        # Honest trace auditing: both low-level attempts are recorded
        self.assertEqual(len(task.traces), 2)
        self.assertEqual(task.traces[0]['tool'], 'extract_pdf_text')
        self.assertEqual(task.traces[0]['status'], 'error')
        self.assertEqual(task.traces[1]['tool'], 'read_attachment')
        self.assertEqual(task.traces[1]['status'], 'completed')

    def test_recovery_with_unambiguous_filename_source(self):
        """read_attachment resolving via unambiguous attached filename also qualifies as same-objective recovery."""
        pdf_file = self.outside_dir / 'spec.pdf'
        self._create_pdf(pdf_file, ['Cover sheet', 'CANARY-SPEC-99 on page 2'])
        self.registry.register([str(pdf_file)], 'chat-f04')

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'spec.pdf', 'page': '2'}},
            {'tool': 'read_attachment', 'arguments': {'source': 'spec.pdf', 'page': '2'}},
            {'final': 'CANARY-SPEC-99 found on page 2 of spec.pdf.'}
        ]

        task = self._make_task(plans, 'Find CANARY-SPEC-99 on page 2 of spec.pdf.')
        self.assertEqual(task.state, 'COMPLETED')
        self.assertIn('CANARY-SPEC-99', task.final)
        self.assertNotIn('Task is partial', task.final)
        self.assertEqual(len(task.traces), 2)

    def test_counterexample_wrong_page_remains_partial(self):
        """Failing on page 2 and succeeding on page 1 does NOT satisfy the objective and remains PARTIAL."""
        pdf_file = self.outside_dir / 'physical-pages.pdf'
        self._create_pdf(pdf_file, ['Page 1 Intro', 'Page 2 Secret: ALPHA-99'])
        record = self.registry.register([str(pdf_file)], 'chat-f04')[0]

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'physical-pages.pdf', 'page': '2'}},
            {'tool': 'read_attachment', 'arguments': {'source': record['id'], 'page': '1'}},
            {'final': 'Page 1 says Page 1 Intro.'}
        ]

        task = self._make_task(plans, 'What is on physical page 2 of physical-pages.pdf?')
        self.assertEqual(task.state, 'PARTIAL')
        self.assertIn('Task is partial', task.final)
        self.assertIn('extract_pdf_text', task.final)

    def test_counterexample_wrong_document_remains_partial(self):
        """Reading docB after failing to read docA does NOT resolve docA's failure."""
        docB = self.outside_dir / 'docB.pdf'
        self._create_pdf(docB, ['docB content on page 1'])
        recB = self.registry.register([str(docB)], 'chat-f04')[0]

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'docA.pdf', 'page': '1'}},
            {'tool': 'read_attachment', 'arguments': {'source': recB['id'], 'page': '1'}},
            {'final': 'I read docB.'}
        ]

        task = self._make_task(plans, 'Read docA.pdf.')
        self.assertEqual(task.state, 'PARTIAL')
        self.assertIn('Task is partial', task.final)
        self.assertIn('extract_pdf_text', task.final)

    def test_counterexample_omitted_scanned_page_remains_partial(self):
        """Scanned PDF page lacking selectable text cannot recover a failed extraction."""
        doc = pymupdf.open()
        p = doc.new_page()  # blank page without text -> scanned requiring OCR
        p.draw_rect(pymupdf.Rect(50, 50, 200, 200))
        scan_pdf = self.outside_dir / 'scanned.pdf'
        doc.save(scan_pdf)
        doc.close()
        rec = self.registry.register([str(scan_pdf)], 'chat-f04')[0]

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'scanned.pdf', 'page': '1'}},
            {'tool': 'read_attachment', 'arguments': {'source': rec['id'], 'page': '1'}},
            {'final': 'Scanned page inspected.'}
        ]

        task = self._make_task(plans, 'Read scanned.pdf.')
        self.assertEqual(task.state, 'PARTIAL')
        self.assertIn('Task is partial', task.final)

    def test_counterexample_unrecovered_failure_remains_partial(self):
        """When multiple files fail and only one is recovered, terminal state remains PARTIAL."""
        pdf_file = self.outside_dir / 'notes.pdf'
        self._create_pdf(pdf_file, ['Content on page 1'])
        rec = self.registry.register([str(pdf_file)], 'chat-f04')[0]

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'notes.pdf', 'page': '1'}},
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'other_unrecovered.pdf', 'page': '1'}},
            {'tool': 'read_attachment', 'arguments': {'source': rec['id'], 'page': '1'}},
            {'final': 'Finished reading notes.'}
        ]

        task = self._make_task(plans, 'Read notes.pdf and other_unrecovered.pdf.')
        self.assertEqual(task.state, 'PARTIAL')
        self.assertIn('Task is partial', task.final)
        self.assertIn('extract_pdf_text', task.final)

    def test_counterexample_mutation_failure_cannot_be_recovered_by_read(self):
        """Direct verification that is_same_objective_recovered rejects write mutation failures."""
        failed_write = {
            'tool': 'write_local_file',
            'operationId': 'w1',
            'args': {'path': 'output.txt', 'content': 'data'},
            'result': {'error': 'Permission denied'}
        }
        succ_read = {
            'tool': 'read_attachment',
            'operationId': 'r1',
            'args': {'source': 'attachment:notes', 'page': '1'},
            'result': {'name': 'notes.pdf', 'coverage_complete': True, 'omitted': False}
        }
        self.assertFalse(is_same_objective_recovered(failed_write, [succ_read], [{'id': 'attachment:notes', 'name': 'notes.pdf'}]))

    def test_legitimate_workspace_pdf_extract_pdf_text_succeeds(self):
        """A legitimate PDF inside the workspace is extracted normally via extract_pdf_text."""
        ws_pdf = self.workspace_dir / 'internal_report.pdf'
        self._create_pdf(ws_pdf, ['Workspace page 1: INTERNAL-99', 'Workspace page 2'])

        plans = [
            {'tool': 'extract_pdf_text', 'arguments': {'path': 'internal_report.pdf', 'page': '1'}},
            {'final': 'Marker is INTERNAL-99.'}
        ]

        task = self._make_task(plans, 'Extract page 1 of internal_report.pdf.')
        self.assertEqual(task.state, 'COMPLETED')
        self.assertIn('INTERNAL-99', task.final)
        self.assertNotIn('Task is partial', task.final)
        self.assertEqual(len(task.traces), 1)
        self.assertEqual(task.traces[0]['tool'], 'extract_pdf_text')
        self.assertEqual(task.traces[0]['status'], 'completed')

    def test_extract_pdf_text_guidance_for_attached_document(self):
        """When extract_pdf_text fails on a file not in workspace, error includes clear read_attachment advice."""
        with self.assertRaises(FileNotFoundError) as ctx:
            self.tools.call('extract_pdf_text', {'path': 'missing-attachment.pdf'})
        self.assertIn("Workspace file not found: 'missing-attachment.pdf'", str(ctx.exception))
        self.assertIn("For attached conversation documents, use read_attachment", str(ctx.exception))

    def test_unregistered_attachment_id_fails_closed(self):
        """Unknown attachment source raises PermissionError."""
        with self.assertRaises(PermissionError):
            self.specialists.call('read_attachment', {'source': 'attachment:nonexistent'}, threading.Event())

    def test_image_attachment_passed_to_read_attachment_fails_closed(self):
        """Passing an image attachment to read_attachment raises ValueError."""
        img_path = self.outside_dir / 'test.png'
        Image.new('RGB', (32, 32), 'blue').save(img_path)
        rec = self.registry.register([str(img_path)], 'chat-f04')[0]
        with self.assertRaisesRegex(ValueError, 'attachment is an image'):
            self.specialists.call('read_attachment', {'source': rec['id']}, threading.Event())

    def test_cancellation_emits_canceled_state(self):
        """A cancelled task emits CANCELED and terminates promptly."""
        it = iter([{'tool': 'extract_pdf_text', 'arguments': {'path': 'any.pdf'}}])
        client = LocalClient(self.tools)
        task = AgentRuntime(
            lambda *_: json.dumps(next(it)),
            self.workspace_dir,
            None,
            'chat-f04',
            lambda _: None,
            client_factory=lambda *_, **__: client
        )
        task.cancel()
        asyncio.run(task.run('Read any.pdf'))
        self.assertEqual(task.state, 'CANCELED')
        self.assertIn('cancelled', task.final.casefold())

    def test_request_tool_policy_includes_attachment_hints(self):
        """request_tool_policy surfaces attachment hints for attached documents."""
        resources = [
            {'id': 'attachment:1', 'name': 'guide.pdf', 'mediaType': 'application/pdf'},
            {'id': 'attachment:2', 'name': 'photo.png', 'mediaType': 'image/png'}
        ]
        policy = request_tool_policy('Review the attached guide.pdf and describe the photo.png', resources)
        self.assertTrue(policy['document'])
        self.assertTrue(policy['visual'])
        self.assertIn('guide.pdf', policy['attachment_hints'])
        self.assertIn('photo.png', policy['attachment_hints'])


    def test_duplicate_filenames_across_attachments_prevents_unambiguous_recovery(self):
        """When two attachments share the same filename, filename-based recovery fails closed."""
        res_list = [
            {'id': 'attachment:alpha1', 'name': 'report.pdf'},
            {'id': 'attachment:beta2', 'name': 'report.pdf'}
        ]
        failed_call = {
            'tool': 'extract_pdf_text',
            'operationId': 'f1',
            'args': {'path': 'report.pdf', 'page': '1'},
            'result': {'error': "Workspace file not found: 'report.pdf'"}
        }
        succ_call = {
            'tool': 'read_attachment',
            'operationId': 's1',
            'args': {'source': 'attachment:alpha1', 'page': '1'},
            'result': {'source': 'attachment:alpha1', 'name': 'report.pdf', 'coverage_complete': True, 'omitted': False}
        }
        # Ambiguous filename: cannot infer that failed call meant attachment:alpha1
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_call], res_list))

    def test_differing_attachment_ids_fails_recovery(self):
        """When failed call specified attachment:alpha1, reading attachment:beta2 does NOT recover."""
        failed_call = {
            'tool': 'read_attachment',
            'operationId': 'f1',
            'args': {'source': 'attachment:alpha1', 'page': '1'},
            'result': {'error': "Attachment read error"}
        }
        succ_call = {
            'tool': 'read_attachment',
            'operationId': 's1',
            'args': {'source': 'attachment:beta2', 'page': '1'},
            'result': {'source': 'attachment:beta2', 'name': 'doc.pdf', 'coverage_complete': True, 'omitted': False}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_call], []))

    def test_permission_denied_failure_never_recovers(self):
        """An access violation or permission denial must never be treated as recovered."""
        failed_call = {
            'tool': 'read_local_file',
            'operationId': 'f1',
            'args': {'path': '../secret.txt'},
            'result': {'error': 'Permission denied: path outside workspace sandbox'}
        }
        succ_call = {
            'tool': 'read_attachment',
            'operationId': 's1',
            'args': {'source': 'attachment:safe', 'page': '1'},
            'result': {'name': 'secret.txt', 'coverage_complete': True, 'omitted': False}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_call], [{'id': 'attachment:safe', 'name': 'secret.txt'}]))

    def test_truncated_or_incomplete_read_fails_recovery(self):
        """A recovery read that is truncated or requires OCR fails recovery."""
        failed_call = {
            'tool': 'extract_pdf_text',
            'operationId': 'f1',
            'args': {'path': 'doc.pdf', 'page': '1'},
            'result': {'error': "Workspace file not found: 'doc.pdf'"}
        }
        res = [{'id': 'attachment:doc', 'name': 'doc.pdf'}]
        # Truncated
        succ_trunc = {
            'tool': 'read_attachment', 'operationId': 's1',
            'args': {'source': 'attachment:doc', 'page': '1'},
            'result': {'name': 'doc.pdf', 'coverage_complete': True, 'omitted': False, 'truncated': True}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_trunc], res))
        # Omitted
        succ_omitted = {
            'tool': 'read_attachment', 'operationId': 's2',
            'args': {'source': 'attachment:doc', 'page': '1'},
            'result': {'name': 'doc.pdf', 'coverage_complete': True, 'omitted': True}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_omitted], res))
        # Scanned pages requiring OCR
        succ_ocr = {
            'tool': 'read_attachment', 'operationId': 's3',
            'args': {'source': 'attachment:doc', 'page': '1'},
            'result': {'name': 'doc.pdf', 'coverage_complete': True, 'omitted': False, 'scannedPagesRequiringOcr': [1]}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_ocr], res))

    def test_cancellation_during_recovery_fails_closed(self):
        """Active cancellation event immediately prevents recovery."""
        cancel = threading.Event()
        cancel.set()
        failed_call = {
            'tool': 'extract_pdf_text',
            'operationId': 'f1',
            'args': {'path': 'doc.pdf', 'page': '1'},
            'result': {'error': "Workspace file not found: 'doc.pdf'"}
        }
        succ_call = {
            'tool': 'read_attachment', 'operationId': 's1',
            'args': {'source': 'attachment:doc', 'page': '1'},
            'result': {'name': 'doc.pdf', 'coverage_complete': True, 'omitted': False}
        }
        self.assertFalse(is_same_objective_recovered(failed_call, [succ_call], [{'id': 'attachment:doc', 'name': 'doc.pdf'}], cancel_event=cancel))

    def test_system_prompt_surfaces_attached_documents_for_initial_selection(self):
        """The agent system prompt includes explicit attached document guidance for initial tool selection."""
        seen_prompts = []
        def capture_model(msgs, *a):
            seen_prompts.append(msgs)
            return '{"final":"done"}'
        task = AgentRuntime(capture_model, self.workspace_dir, None, 'chat-f04', lambda _: None)
        task.resources = [{'id': 'attachment:doc99', 'name': 'quarterly.pdf', 'mediaType': 'application/pdf'}]
        asyncio.run(task.run('Summarize quarterly.pdf'))
        system_content = seen_prompts[0][0]['content']
        self.assertIn('quarterly.pdf', system_content)
        self.assertIn('attachment:doc99', system_content)
        self.assertIn('read_attachment', system_content)


if __name__ == '__main__':
    unittest.main()
