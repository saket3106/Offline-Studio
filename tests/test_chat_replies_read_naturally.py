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


if __name__ == '__main__':
    unittest.main()
