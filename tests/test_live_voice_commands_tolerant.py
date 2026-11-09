import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from live_voice import session_command


class TolerantVoiceExit(unittest.TestCase):
    """Real-app transcripts: 'End this live version.' (misheard 'voice') went to the model."""

    def test_misheard_and_natural_exit_phrases(self):
        for text in ['End this live version.', 'close live voice chat', 'Close this live voice mode.', 'Turn off voice mode',
                     'turn the voice off', 'Okay, goodbye.', "That's all for now.", 'Shut down the voice assistant',
                     'end this live boys mode', 'Quit voice chat']:
            with self.subTest(text=text): self.assertEqual(session_command(text), 'exit')

    def test_ordinary_sentences_are_not_commands(self):
        for text in ['what is a voice chat', 'close my version of the document', 'the latest version is out',
                     'how do I end a voice chat in Discord?', 'I said goodbye to my friend']:
            with self.subTest(text=text): self.assertIsNone(session_command(text))


if __name__ == '__main__':
    unittest.main()
