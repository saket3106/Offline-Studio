"""Bounded synthetic regressions; no models, microphone or production data."""
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from app import App, ChatWorker
from intelligence import analyze_request
from live_voice import voice_response_policy, SpeechPreview, merge_continuation, continuation_messages


class VoicePolicyTests(unittest.TestCase):
    def test_short_turn_keeps_small_budget(self):
        policy = voice_response_policy('Hello, how are you?', 1200)
        self.assertLessEqual(policy['max_tokens'], 192)
        self.assertFalse(policy['long_response'])

    def test_500_word_request_is_not_capped_to_140(self):
        prompt = 'Explain a large language model in 500 words.'
        policy = voice_response_policy(prompt, 900, analyze_request(prompt)['constraints'])
        self.assertGreaterEqual(policy['max_tokens'], 1500)
        self.assertLessEqual(policy['max_tokens'], 2400)
        self.assertTrue(policy['long_response'])
        self.assertNotIn('1 to 2', policy['instruction'])

    def test_whisper_spelled_word_count(self):
        policy = voice_response_policy('Explain it in five hundred words.', 900)
        self.assertTrue(policy['long_response'])
        self.assertGreaterEqual(policy['max_tokens'], 1500)

    def test_large_request_remains_bounded_and_short_explicit_count_is_respected(self):
        self.assertEqual(voice_response_policy('Write 50000 words.', 900)['max_tokens'], 2400)
        self.assertFalse(voice_response_policy('Explain it in 50 words.', 900)['long_response'])
        self.assertLessEqual(voice_response_policy('Explain it in 50 words.', 900)['max_tokens'], 256)

    def test_long_speech_preview_is_bounded_without_repeated_notice(self):
        gate = SpeechPreview(100)
        actual = ''.join(gate.push('This is a complete short sentence. ') for _ in range(30)) + gate.finish()
        self.assertLess(len(actual), 220)
        self.assertEqual(actual.count('full answer'), 1)
        self.assertEqual(gate.push('Stale later text.'), '')

    def test_short_speech_stream_is_immediate(self):
        gate = SpeechPreview()
        self.assertEqual(gate.push('Hello'), 'Hello')
        self.assertEqual(gate.push(' there.'), ' there.')
        self.assertEqual(gate.finish(), '')

    def test_continuation_survives_actual_context_fitter_dropping_old_turns(self):
        from integrated_runtime import _LocalLlamaServer
        runtime=object.__new__(_LocalLlamaServer);runtime.context=4096
        original=[{'role':'system','content':'Answer faithfully.'},
                  {'role':'user','content':'Historical conversation.'},
                  {'role':'assistant','content':'Old answer.'},
                  {'role':'user','content':'Explain local inference in 500 words.'}]
        draft='The exact original paragraph must survive. '*40
        continuation=continuation_messages(original,original[-1]['content'],draft)
        runtime._prompt_tokens=lambda messages: 3000 if len(messages)>2 else 700
        fitted,_,_,shortened=runtime._fit_messages(continuation,1600,lambda _:None,None)
        self.assertTrue(shortened)
        self.assertIn(draft,fitted[-1]['content'])
        self.assertIn('Explain local inference in 500 words.',fitted[-1]['content'])
        self.assertEqual(original[-1]['content'],'Explain local inference in 500 words.')

    def test_exact_overlap_removed_without_fuzzy_content_deletion(self):
        prefix = 'The first paragraph explains the original source. '
        self.assertEqual(merge_continuation(prefix, prefix + 'The next paragraph adds detail.'), prefix.rstrip() + ' The next paragraph adds detail.')
        self.assertEqual(merge_continuation(prefix, 'A distinct paragraph.'), prefix.rstrip() + ' A distinct paragraph.')


class ScriptedEngine:
    cfg = {}
    def __init__(self, answers, finishes, failure=None, cancel=None):
        self.answers, self.finishes, self.failure, self.cancel = answers, finishes, failure, cancel
        self.requests = []
        self.runtime = SimpleNamespace(last_generation_diagnostics={})
    def ensure_chat(self, *a, **kw): return 'local'
    def chat_completion(self, messages, **kw):
        index = len(self.requests)
        self.requests.append((messages, kw))
        if index and self.failure: raise RuntimeError(self.failure)
        if index and self.cancel:
            self.cancel.set()
            raise RuntimeError('Cancelled')
        answer = self.answers[index]
        self.runtime.last_generation_diagnostics = {'finish_reason': self.finishes[index], 'generated_token_count': 120}
        for chunk in [answer[:25], answer[25:]]:
            if chunk: kw['on_token'](chunk)
        return answer


class VoiceRecoveryTests(unittest.TestCase):
    def run_worker(self, engine):
        prompt = 'Explain how a local language model generates text.'
        analysis = analyze_request(prompt)
        analysis.update(voice_mode=True, agent_tools=[], max_retries=0, selective_review=False,
                        profile={'max_tokens': 1600, 'temperature': .2})
        worker = ChatWorker('local', [{'role':'user','content':prompt}], engine, analysis)
        done, failed, partials, tokens, metrics, cancelled = [], [], [], [], [], []
        worker.done.connect(done.append); worker.failed.connect(failed.append)
        worker.partial.connect(partials.append); worker.token.connect(tokens.append)
        worker.metrics.connect(metrics.append); worker.cancelled.connect(cancelled.append)
        if engine.cancel: engine.cancel = worker.cancel_event
        worker.run()
        return done, failed, partials, tokens, metrics, cancelled

    def test_continuation_preserves_first_draft_and_has_no_tool_authority(self):
        prefix = 'The original paragraph remains visible. '
        engine = ScriptedEngine([prefix, prefix + 'The answer now finishes.'], ['length','stop'])
        done, failed, partials, tokens, metrics, _ = self.run_worker(engine)
        self.assertFalse(failed); self.assertEqual(len(engine.requests), 2)
        self.assertEqual(done, [(prefix + 'The answer now finishes.').strip()])
        self.assertNotIn('', partials)
        self.assertEqual(''.join(tokens), prefix)
        self.assertEqual(engine.requests[1][1]['allowed_tools'], [])
        self.assertIn('Continue', engine.requests[1][0][-1]['content'])
        self.assertEqual(metrics[-1]['continuation_attempts'], 1)

    def test_second_cutoff_keeps_text_and_reports_incomplete(self):
        engine = ScriptedEngine(['The first useful paragraph.', 'The second useful paragraph.'], ['length','length'])
        done, failed, partials, _, metrics, _ = self.run_worker(engine)
        self.assertFalse(failed); self.assertEqual(len(engine.requests), 2)
        self.assertIn('first useful', done[0]); self.assertIn('second useful', done[0])
        self.assertIn('Response incomplete', done[0])
        self.assertEqual(metrics[-1]['validation_status'], 'partial')
        self.assertTrue(metrics[-1]['response_incomplete'])
        self.assertNotIn('', partials)

    def test_failed_continuation_retains_original_without_internal_error_in_answer(self):
        engine = ScriptedEngine(['Useful original paragraph.'], ['length'], failure='internal socket detail')
        done, failed, _, _, metrics, _ = self.run_worker(engine)
        self.assertFalse(failed); self.assertIn('Useful original paragraph.', done[0])
        self.assertNotIn('internal socket', done[0]); self.assertTrue(metrics[-1]['response_incomplete'])

    def test_empty_continuation_is_partial_not_a_complete_repeated_prefix(self):
        engine=ScriptedEngine(['Useful original paragraph.',''],['length','stop'])
        done,failed,_,_,metrics,_=self.run_worker(engine)
        self.assertFalse(failed);self.assertIn('Useful original paragraph.',done[0])
        self.assertTrue(metrics[-1]['response_incomplete'])
        self.assertEqual(metrics[-1]['validation_status'],'partial')

    def test_exhausted_shared_token_budget_keeps_prefix_without_extra_call(self):
        class ExhaustedEngine(ScriptedEngine):
            def chat_completion(self,messages,**kw):
                answer=super().chat_completion(messages,**kw)
                self.runtime.last_generation_diagnostics['generated_token_count']=8000
                return answer
        engine=ExhaustedEngine(['Useful original paragraph.'],['length'])
        done,failed,_,_,metrics,_=self.run_worker(engine)
        self.assertFalse(failed);self.assertIn('Useful original paragraph.',done[0])
        self.assertEqual(len(engine.requests),1)
        self.assertTrue(metrics[-1]['response_incomplete'])

    def test_cancellation_keeps_original_and_never_finalizes_success(self):
        engine = ScriptedEngine(['Useful original paragraph.'], ['length'], cancel=threading.Event())
        done, failed, _, _, _, cancelled = self.run_worker(engine)
        self.assertFalse(done); self.assertFalse(failed)
        self.assertEqual(cancelled, ['Useful original paragraph.'])


class VoiceSynchronizationTests(unittest.TestCase):
    def owner(self):
        speech = SimpleNamespace(streaming=True, message_id='response', push_stream_chunk=Mock(), stop=Mock(), finish_stream=Mock())
        backend = SimpleNamespace(operation_event_id='response', voice_mode_active=True,
            frontend_bridge=SimpleNamespace(speech=speech), _voice_stream_visible='',
            _voice_speech_gate=SpeechPreview(), _voice_speech_suppressed=False)
        return backend, speech

    def test_snapshot_append_does_not_replay_spoken_prefix(self):
        b, speech = self.owner()
        App._sync_voice_stream(b, 'First sentence. ')
        App._sync_voice_stream(b, 'First sentence. Second sentence.')
        App._sync_voice_stream(b, 'First sentence. Second sentence.')
        self.assertEqual([c.args[0] for c in speech.push_stream_chunk.call_args_list], ['First sentence. ', 'Second sentence.'])

    def test_final_whitespace_normalization_does_not_interrupt_speech(self):
        b, speech = self.owner()
        App._sync_voice_stream(b, 'Original paragraph. ')
        App._sync_voice_stream(b, 'Original paragraph.')
        speech.stop.assert_not_called()
        self.assertFalse(b._voice_speech_suppressed)

    def test_replaced_draft_invalidates_audio_without_replaying(self):
        b, speech = self.owner()
        App._sync_voice_stream(b, 'Earlier draft already spoken.')
        App._sync_voice_stream(b, 'Corrected written answer.')
        speech.stop.assert_called_once(); self.assertTrue(b._voice_speech_suppressed)
        self.assertEqual(speech.push_stream_chunk.call_count, 1)

    def test_foreign_message_cannot_receive_current_audio(self):
        b, speech = self.owner(); speech.message_id='old'
        App._sync_voice_stream(b, 'New text.')
        speech.push_stream_chunk.assert_not_called()

    def test_stale_failure_cancel_and_metrics_cannot_mutate_new_turn(self):
        old=SimpleNamespace(operation_event_id='old',chat_id='old-chat')
        backend=SimpleNamespace(sender=lambda:old,operation_event_id='new',current='new-chat')
        for handler,arg in [(App.answer_failed,'old failure'),(App.worker_cancelled,'old text'),
                            (App.on_chat_metrics,{}),(App.on_chat_activity,{}),(App.on_worker_progress,'Old')]:
            handler(backend,arg)  # Minimal owner intentionally has no mutating methods.

    def test_stale_worker_identity_is_rejected(self):
        old = SimpleNamespace(operation_event_id='old', chat_id='chat-a')
        b = SimpleNamespace(sender=lambda:old, operation_event_id='new', current='chat-a')
        self.assertFalse(App._owns_chat_callback(b))
        b.operation_event_id='old'; b.current='chat-b'
        self.assertFalse(App._owns_chat_callback(b))


class PromptAssemblyTests(unittest.TestCase):
    def test_real_app_send_assembles_long_voice_request_before_worker_start(self):
        import os, tempfile
        from pathlib import Path
        from unittest.mock import patch
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        import app
        qt=QApplication.instance() or QApplication([])
        captured=[]
        class PreparedFixture(Exception): pass
        def capture(model,messages,engine,analysis):
            captured.append((messages,analysis))
            raise PreparedFixture('dispatch boundary; no model launched')
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB_PATH',Path(folder)/'fixture.sqlite3'),patch.object(app,'DATA_DIR',Path(folder)):
            backend=app.App()
            try:
                backend.voice_mode_active=True
                with patch.object(app,'ChatWorker',side_effect=capture):
                    with self.assertRaises(PreparedFixture):
                        backend.send(text_override='Explain how local language models work in 500 words.')
                self.assertEqual(len(captured),1)
                messages,analysis=captured[0]
                self.assertTrue(analysis['voice_mode'])
                self.assertTrue(analysis['voice_long_response'])
                self.assertGreaterEqual(analysis['profile']['max_tokens'],1500)
                self.assertNotIn('1 to 2 spoken sentences',messages[0]['content'])
                self.assertIn('500 words',messages[-1]['content'])
            finally:
                backend.voice_mode_active=False;backend.busy=False;backend.typing_timer.stop();backend.close();qt.processEvents();backend.store.con.close()


class PartialJournalTests(unittest.TestCase):
    def test_incomplete_answer_is_not_recorded_as_operation_success(self):
        import os,tempfile
        from pathlib import Path
        from unittest.mock import patch
        os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
        from PySide6.QtWidgets import QApplication
        import app
        qt=QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB_PATH',Path(folder)/'fixture.sqlite3'),patch.object(app,'DATA_DIR',Path(folder)):
            backend=app.App()
            try:
                backend.operation_event_id='partial-fixture'
                backend._response_metrics={'partial-fixture':{'response_incomplete':True}}
                backend.store.workspace.begin('partial-fixture','chat')
                backend.busy=True;backend.set_busy(False,'Ready')
                row=backend.store.con.execute('SELECT state,error_code FROM operation_journal WHERE id=?',('partial-fixture',)).fetchone()
                self.assertEqual(row,('partial','RESPONSE_INCOMPLETE'))
                self.assertFalse(backend.busy)
            finally:
                backend.busy=False;backend.close();qt.processEvents();backend.store.con.close()


if __name__ == '__main__': unittest.main()
