"""One message = one answer (owner evidence 00_ONE_SEND_FOUR_REWRITES).

A fake LLM backend counts calls. For "explain X in 100 words" / "in 500 words"
there must be exactly one answer call, streamed text is never cleared, and an
approximate length request never produces a validation warning.
"""
import unittest
from types import SimpleNamespace

from intelligence import analyze_request
from memory_manager import calculate_dynamic_context_budget, length_target_output_tokens
from validators import trim_to_complete_sentence, word_target_status


def words(n):
    body = ' '.join(['Large language models learn statistical patterns from text'] * (n // 8 + 1)).split()[:n]
    return ' '.join(body).rstrip('.') + '.'


class CountingEngine:
    def __init__(self, answers, finish='stop'):
        self.answers = list(answers); self.calls = []; self.finish = finish
        self.runtime = SimpleNamespace(last_generation_diagnostics={})

    def ensure_chat(self, *a, **k): return 'local'

    def chat_completion(self, messages, **kwargs):
        self.calls.append(kwargs)
        text = self.answers.pop(0) if self.answers else 'unexpected extra call'
        if kwargs.get('on_token'):
            for piece in text.split(' '): kwargs['on_token'](piece + ' ')
        self.runtime.last_generation_diagnostics = {'generated_token_count': len(text.split()), 'finish_reason': self.finish}
        return text


def run(prompt, engine, voice=False):
    from app import ChatWorker
    analysis = analyze_request(prompt)
    analysis.update(agent_tools=[], selective_review=False)
    if voice: analysis.update(voice_mode=True)
    worker = ChatWorker('local', [{'role': 'user', 'content': prompt}], engine, analysis)
    done, failed, metrics, partials = [], [], [], []
    worker.done.connect(done.append); worker.failed.connect(failed.append)
    worker.metrics.connect(metrics.append); worker.partial.connect(partials.append)
    worker.run()
    return analysis, done, failed, metrics, partials


class OneAnswerTests(unittest.TestCase):
    def test_in_n_words_is_a_target_not_an_exact_count(self):
        for n in (100, 500):
            c = analyze_request(f'explain what is a LLM model in {n} words')['constraints']
            self.assertIsNone(c['word_count_exact']); self.assertEqual(c['word_count_target'], n)
        self.assertEqual(analyze_request('Describe AI in exactly 12 words.')['constraints']['word_count_exact'], 12)
        self.assertEqual(analyze_request('Write a sentence about cats in 10 words.')['constraints']['word_count_exact'], 10)

    def test_default_analysis_never_retries(self):
        self.assertEqual(analyze_request('explain what is a LLM model in 500 words')['max_retries'], 0)

    def test_exactly_one_answer_call_for_length_requests(self):
        for n, produced in ((100, 70), (500, 430)):  # off-target but within the soft tolerance window or not: never regenerated
            engine = CountingEngine([words(produced)])
            _, done, failed, metrics, partials = run(f'explain what is a LLM model in {n} words', engine)
            self.assertFalse(failed); self.assertEqual(len(engine.calls), 1, f'{n}-word request made {len(engine.calls)} calls')
            self.assertEqual(len(done), 1); self.assertNotIn('unexpected extra call', done[0])
            self.assertNotIn('', partials, 'streamed text was cleared')
            self.assertNotEqual(metrics[-1].get('validation_status'), 'partial')

    def test_voice_turn_makes_one_answer_call(self):
        engine = CountingEngine(['Machine learning lets computers learn patterns from data.'])
        _, done, failed, _, partials = run('what is machine learning', engine, voice=True)
        self.assertFalse(failed); self.assertEqual(len(engine.calls), 1); self.assertNotIn('', partials)

    def test_length_cutoff_is_trimmed_not_regenerated(self):
        engine = CountingEngine(['First complete sentence here. Second sentence is also complete. And then the model stopped in the mid'], finish='length')
        _, done, failed, metrics, _ = run('explain transformers in 500 words', engine)
        self.assertFalse(failed); self.assertEqual(len(engine.calls), 1)
        self.assertTrue(done[0].rstrip().endswith('complete.')); self.assertTrue(metrics[-1]['response_truncated_by_length'])

    def test_output_budget_from_requested_words(self):
        self.assertEqual(length_target_output_tokens(100), 1126)  # floor 1024 x 1.1
        self.assertEqual(length_target_output_tokens(500), 1144)  # 500*1.6*1.3*1.1
        self.assertLessEqual(length_target_output_tokens(5000, 4096), 4096 - 512)
        out, _ = calculate_dynamic_context_budget(category='normal', total_context=8192, requested_words=500)
        self.assertGreaterEqual(out, 1144)

    def test_soft_word_target_and_sentence_trim(self):
        self.assertTrue(word_target_status(words(420), 500)['withinTolerance'])
        self.assertFalse(word_target_status(words(200), 500)['withinTolerance'])
        self.assertEqual(trim_to_complete_sentence('One. Two is done. Three is cut mid'), 'One. Two is done.')
        self.assertEqual(trim_to_complete_sentence('```py\nx=1'), '```py\nx=1')


if __name__ == '__main__':
    unittest.main()
