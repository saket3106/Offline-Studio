"""Follow-up instructions edit the image the assistant just showed (owner report 2026-11-09)."""
import json, tempfile, unittest
from pathlib import Path
from router import is_image_edit_instruction, image_followup_edit, latest_assistant_image


class ImageFollowupTests(unittest.TestCase):
    def test_edit_wording(self):
        for text in ['make the sky orange', 'now make it green', 'edit it and make the apple green', 'put sunglasses on the cat',
                     'add a hat to him', 'give it a red background', 'Okay, can you make it look like a painting?',
                     'turn it into a cartoon', 'remove the background', 'without the table', 'same image but with a blue car']:
            with self.subTest(text=text):
                self.assertTrue(is_image_edit_instruction(text))
        for text in ['make a poem about it', 'make it my wallpaper', 'what is in this image?', 'describe it', 'thanks it looks great',
                     'generate a new image of a dog', 'make another one', 'draw a cat', 'how do I save it', 'Make one of a dog instead']:
            with self.subTest(text=text):
                self.assertFalse(is_image_edit_instruction(text))

    def test_only_the_latest_assistant_image_counts(self):
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / 'a.png'; img.write_bytes(b'png')
            rows = [('user', 'draw an apple', ''), ('assistant', 'Generated image', str(img))]
            self.assertEqual(image_followup_edit('make it green', rows), str(img))
            self.assertEqual(latest_assistant_image([('assistant', 'x', json.dumps([str(img)]))]), str(img))
            later = rows + [('user', 'tell me a joke', ''), ('assistant', 'Why did...', '')]
            self.assertIsNone(image_followup_edit('make it green', later))
            self.assertIsNone(image_followup_edit('make another one', rows))


if __name__ == '__main__':
    unittest.main()
