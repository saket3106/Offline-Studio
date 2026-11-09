"""Live Voice ends on natural farewells and on commands wrapped in pleasantries (owner request 2026-11-09)."""
import threading, unittest
from types import SimpleNamespace
from unittest.mock import Mock
from live_voice import session_command, voice_intent_candidate, classify_voice_intent


class FarewellExitTests(unittest.TestCase):
    def test_measured_and_requested_phrases_exit(self):
        for text in ['No nothing. Okay. Thank you. Nice talking to you. End this live worship.',
                     "Okay now enough for today, we'll talk tomorrow.", 'end live mode', 'end this mode',
                     'Okay, thank you, end voice chat.', 'Good night.', 'Alright, see you tomorrow.',
                     "Let's call it a day.", 'Okay bye, talk to you later.', 'I have to go now. Bye.',
                     "That's enough for today.", 'Thank you so much. Good night.',
                     'No nothing, okay, thank you, nice talking to you, and this live voice.', 'And this voice chat.']:
            with self.subTest(text=text):
                self.assertEqual(session_command(text), 'exit')

    def test_ordinary_turns_are_unchanged(self):
        for text in ['Good morning', 'Thank you', 'What is enough sleep?', 'Nice talking to you. Tell me a joke.',
                     'I said goodbye to my friend', 'End it.', 'End voice mode. Tell me a story.',
                     'Pause listening. End voice chat.', 'How do I end a voice chat?', 'and then what happened',
                     'and the voice was nice']:
            with self.subTest(text=text):
                self.assertIsNone(session_command(text))

    def test_model_judges_other_closings(self):
        self.assertTrue(voice_intent_candidate('we will talk tomorrow maybe'))
        runtime = SimpleNamespace(ready=True, context=2048, complete=Mock(return_value='{"intent":"EXIT_VOICE","confidence":"high"}'))
        engine = SimpleNamespace(runtime=runtime, cfg={'chat_backend': 'bundled'}, loaded_model='m', resource_lock=threading.RLock(),
                                 lock=threading.RLock(), _cancel_idle_timer=Mock(), _schedule_idle_unload=Mock(), _active_inference_count=0)
        result = classify_voice_intent(engine, 'Alright buddy, we can continue this tomorrow', threading.Event())
        self.assertEqual(result['action'], 'exit')


if __name__ == '__main__':
    unittest.main()
