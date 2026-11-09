"""Voice-mode titling, research skip and state labels (owner evidence 01/02/14)."""
import unittest

from app import answer_title
from live_voice import voice_response_policy


class VoiceTitleTests(unittest.TestCase):
    def test_title_comes_from_the_answer_not_the_transcript(self):
        self.assertEqual(answer_title('Machine learning is a way for computers to learn patterns.'), 'Machine learning')
        self.assertEqual(answer_title('Sure! The capital of France is Paris.'), 'The capital of France')
        self.assertEqual(answer_title('Yes.'), '')
        self.assertLessEqual(len(answer_title('Quantum computers use qubits to represent many states at once.').split()), 6)

    def test_short_spoken_answers_by_default(self):
        policy = voice_response_policy('what is machine learning', 900)
        self.assertFalse(policy['long_response']); self.assertLessEqual(policy['max_tokens'], 192)
        self.assertIn('1 to 4 short sentences', policy['instruction']); self.assertIn('No markdown', policy['instruction'])

    def test_explicit_length_is_still_honoured(self):
        self.assertTrue(voice_response_policy('explain transformers in 500 words', 4000)['long_response'])


if __name__ == '__main__':
    unittest.main()
