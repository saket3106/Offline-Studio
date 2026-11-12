"""Owner video 2026-11-12: "Summarize our chat" answered with an evidence ledger full of codes
(M438.C15, ISO timestamps, code fragments, "Diagnostic: tools-…"). Replies must read like an online
assistant: the current chat is summarized directly, plain questions skip tools, and answers built
from past chats are readable prose with numbered source chips."""
import re
import unittest

from conversation_memory import history_claim_evidence_view, history_evidence_fallback, memory_intent, readable_history_date
from router import get_relevant_tools, route_request


def src(i, text, kind='USER_STATEMENT', role='user', **extra):
    return dict({'id': 'M' + str(i), 'chatId': 'one', 'url': 'offlinegpt://chat/one?message=' + str(i),
                 'date': '2026-11-07T21:51:27+05:30', 'created': i, 'role': role, 'evidenceKind': kind, 'excerpt': text}, **extra)


class CurrentChatScopeTests(unittest.TestCase):
    def test_our_chat_means_this_chat(self):
        for text in ('Summarize our chat in one sentence.', 'Give me a recap of the conversation so far'):
            intent = memory_intent(text)
            self.assertTrue(intent.get('currentOnly'), text)

    def test_past_chats_still_search_history(self):
        for text in ('summarize our previous conversation', 'what did we discuss in our chats', 'summarize our chat from last week'):
            self.assertTrue(memory_intent(text).get('retrieve'), text)


class PlainQuestionsSkipToolsTests(unittest.TestCase):
    def tools(self, text):
        return get_relevant_tools(route_request(text), text) or []

    def test_time_words_that_are_not_clock_questions(self):
        for text in ('What is the time difference between them?', 'Explain the time complexity of quicksort',
                     'Which time zone is London in?'):
            self.assertFalse(route_request(text).get('wants_datetime'), text)
            self.assertNotIn('datetime', self.tools(text), text)

    def test_real_clock_questions_still_use_the_clock(self):
        for text in ('what time is it', 'What is the time in Tokyo?', 'what day is it today'):
            self.assertTrue(route_request(text).get('wants_datetime'), text)

    def test_substrings_do_not_pull_in_tools(self):
        for text in ('What is the most popular program?', 'How are you today?', 'Write a program for the Ramayana quiz'):
            self.assertEqual([t for t in self.tools(text) if t in ('datetime', 'system_info')], [], text)


class ReadableHistoryAnswerTests(unittest.TestCase):
    def test_answer_is_prose_without_internal_codes(self):
        records = [src(1, 'Please make image generation faster.', kind='USER_REQUEST'),
                   src(2, 'def total(nums):'), src(3, '```python'),
                   src(4, 'I tested the new cache and the second reply came back in under a second.'),
                   src(5, 'Image finished.', kind='APPLICATION_IMAGE_TELEMETRY', role='assistant', runtimeFacts={'duration_seconds': 41.5})]
        text = history_claim_evidence_view(records, 'tools-51235e756fac')
        self.assertNotRegex(text, r'\bM\d+\.(?:C\d+|OP)\b')
        self.assertNotIn('Diagnostic', text)
        self.assertNotIn('tools-51235e756fac', text)
        self.assertNotRegex(text, r'\d{4}-\d{2}-\d{2}T')
        self.assertNotIn('def total', text)
        self.assertNotIn('python', text)
        self.assertIn('7 Nov 2026', text)
        self.assertIn('**You**', text)
        self.assertIn('41.5 seconds', text)
        self.assertIn('[M4](offlinegpt://chat/one?message=4)', text)
        self.assertIn('2 code snippets or short fragments', text)
        self.assertIn('not confirmed as done', text)

    def test_every_quoted_line_carries_a_source(self):
        record = src(1, 'I fixed the parser. Then I tested the cache. The reply was quicker.')
        for line in history_claim_evidence_view([record]).splitlines():
            if '“' in line:
                self.assertIn('[M1]', line)

    def test_nothing_usable_gives_a_helpful_sentence(self):
        text = history_claim_evidence_view([src(1, 'x = 0'), src(2, '```')])
        self.assertIn('couldn’t find', text)
        self.assertNotIn('M1', text)

    def test_fallback_is_prose_too(self):
        text = history_evidence_fallback([src(1, 'We switched the image model to the faster one.')], 'tools-abc')
        self.assertNotIn('Diagnostic', text)
        self.assertNotIn('USER_STATEMENT', text)
        self.assertIn('7 Nov 2026', text)
        self.assertIn('[M1]', text)

    def test_readable_dates(self):
        self.assertEqual(readable_history_date('2026-01-05T08:00:00'), '5 Jan 2026')
        self.assertEqual(readable_history_date('unknown (imported source)'), 'unknown (imported source)')


RAMBLE = ("**Japan** is further north than **France**.\n\n**Correction and Clarification:**\nUpon re-evaluating the "
          "coordinates, France is further north. But wait, let's double-check the northernmost point of Japan.\n\n"
          "*Wait, let me re-verify the northernmost point of France.* No, that is the westernmost point.")


class SelfCorrectionGuardTests(unittest.TestCase):
    def test_a_draft_arguing_with_itself_is_detected(self):
        from validators import self_correction_loop
        self.assertTrue(self_correction_loop(RAMBLE))

    def test_normal_answers_and_code_are_not(self):
        from validators import self_correction_loop
        for text in ('Tokyo is the capital of Japan. Actually, it became the capital in 1868.',
                     'Wait times at the clinic are long. Let me explain the options.',
                     '```python\n# wait, let me re-check\n# wait\nwait()\n```\nThis loop waits for the job.',
                     '"Wait," she said. The door opened.'):
            self.assertFalse(self_correction_loop(text), text)

    def test_stop_when_never_sets_the_users_cancel(self):
        import threading
        from tool_workflow import StopWhen
        user, flag = threading.Event(), [False]
        stop = StopWhen(user, flag)
        self.assertFalse(stop.is_set())
        flag[0] = True
        self.assertTrue(stop.is_set())
        self.assertFalse(user.is_set())

    def test_worker_stops_the_ramble_and_returns_the_thought_through_answer(self):
        from types import SimpleNamespace
        from app import ChatWorker
        from intelligence import analyze_request

        class StreamingEngine:
            def __init__(self):
                self.requests = []; self.runtime = SimpleNamespace(last_generation_diagnostics={})

            def ensure_chat(self, *args, **kwargs):
                return 'local'

            def chat_completion(self, messages, on_token=None, cancel_event=None, **kwargs):
                self.requests.append(kwargs)
                if len(self.requests) == 1:
                    for word in (RAMBLE + ' Wait, let me re-check again. ' * 40).split(' '):
                        if cancel_event is not None and cancel_event.is_set():
                            raise RuntimeError('Cancelled')
                        on_token(word + ' ')
                    return RAMBLE
                self.runtime.last_generation_diagnostics = {'finish_reason': 'stop'}
                answer = 'France is further north: its mainland reaches about 51°N, while Japan reaches about 45.5°N.'
                for word in answer.split(' '):
                    on_token(word + ' ')
                return answer

        prompt = 'Which is further north, Japan or France?'
        analysis = analyze_request(prompt); analysis.update(max_retries=0, selective_review=False, agent_tools=[])
        engine = StreamingEngine()
        worker = ChatWorker('local', [{'role': 'user', 'content': prompt}], engine, analysis)
        done, failed = [], []
        worker.done.connect(done.append); worker.failed.connect(failed.append); worker.run()
        self.assertFalse(failed)
        self.assertEqual(len(engine.requests), 2)
        self.assertEqual(engine.requests[1].get('reasoning_effort'), 'high')
        self.assertGreaterEqual(engine.requests[1].get('max_tokens'), 2400)
        self.assertIn('France is further north', done[0])
        self.assertNotIn('re-verify', done[0])

    def test_chat_worker_retries_once_with_hidden_thinking(self):
        from pathlib import Path
        text = (Path(__file__).resolve().parents[1] / 'app.py').read_text(encoding='utf-8')
        self.assertIn('cancel_event=StopWhen(workflow_cancel,ramble_stop)', text)
        self.assertIn("**({'reasoning_effort':'high'} if thinking_retry[0] else", text)
        self.assertIn('not thinking_retry[0] and recovery_prefix[0] is None and (ramble_stop[0] or self_correction_loop(visible))', text)


if __name__ == '__main__':
    unittest.main()
