"""An image in the chat (or left attached) is context, not the decision (owner report 2026-11-11)."""
import threading
import unittest

from image_pipeline import ImageOperation, select_image_operation
from router import (classify_image_turn, image_turn_fallback, image_turn_intent, parse_image_turn)

LONG_NEW_PROMPT = ("Create a hyper realistic cinematic image of a futuristic city at night, enhance the neon reflections on the wet "
                   "road, scale the skyscrapers massively, crop top girl walking with an umbrella in the foreground, "
                   "volumetric fog, 8k detail, shot on a 35mm lens with shallow depth of field")


class ImageTurnIntentTests(unittest.TestCase):
    def check(self, cases, **context):
        for text, expected in cases:
            with self.subTest(text=text, **context):
                self.assertEqual(image_turn_intent(text, **context), expected)

    def test_new_pictures_stay_new_after_an_image(self):
        self.check([
            ('generate an image of a dragon flying over a castle at sunset', 'generate'),
            ('draw a cat wearing a hat', 'generate'),
            ('paint a sunset over the ocean', 'generate'),
            ('make another one', 'generate'),
            ('Now create a new picture of a mountain lake', 'generate'),
            ('I want a picture of a lighthouse in a storm', 'generate'),
            (LONG_NEW_PROMPT, 'generate'),
        ], recent=True)

    def test_new_chat_picture_requests_without_the_word_image(self):
        # Found in the real app: "draw a red apple on a wooden table" was answered with ASCII art.
        self.check([
            ('draw a red apple on a wooden table', 'generate'), ('paint a sunset over the ocean', 'generate'),
            ('illustrate a cat astronaut', 'generate'), ('generate a red sports car at sunset', 'generate'),
            ('generate 5 ideas for a startup', 'none'), ('generate a list of names', 'none'),
            ('imagine a world without cars and describe it', 'none'), ('sketch out a plan for my week', 'none'),
            ('draw up a contract', 'none'), ('render the table in markdown', 'none'), ('write a poem about the sea', 'none'),
        ])

    def test_a_mistakenly_attached_image_does_not_hijack_a_new_prompt(self):
        self.check([
            ('generate an image of a dog playing in snow', 'generate'),
            (LONG_NEW_PROMPT, 'generate'),
        ], attached=True, recent=True)

    def test_edits_of_the_current_image(self):
        long_edit = ('change the background to a beach with palm trees and a sunset, keep the person exactly the same, make the '
                     'lighting warm golden hour with soft shadows and add a few birds far away in the sky')
        self.check([
            ('make the sky orange', 'edit'), ('now make it green', 'edit'), ('put sunglasses on the cat', 'edit'),
            ('add a hat to him', 'edit'), ('remove the background', 'edit'), ('paint it red', 'edit'),
            ('create a variation of this image', 'edit'), ('same image but with a blue car', 'edit'),
            (long_edit, 'edit'),
        ], recent=True)

    def test_deterministic_operations_need_the_command(self):
        self.check([
            ('resize it to 1024x768', 'resize'), ('make it 1920x1080', 'resize'), ('crop the top part', 'crop'),
            ('upscale to 4k', 'upscale'), ('enhance it', 'upscale'), ('please crop this photo', 'crop'),
        ], recent=True)
        # Words inside a description never pick an operation.
        self.check([
            ('Write an essay about how startups scale', 'none'),
            ('a large scale battle scene with knights', 'none'),
            ('explain how to crop a photo in photoshop', 'none'),
        ])

    def test_the_attach_an_image_reply_needs_a_request_aimed_at_an_image(self):
        self.assertEqual(image_turn_intent('resize this image to 512x512'), 'resize')
        self.assertEqual(image_turn_intent('crop this photo'), 'crop')
        self.assertEqual(image_turn_intent(LONG_NEW_PROMPT), 'generate')

    def test_questions_and_chat(self):
        self.check([('what breed is this?', 'describe'), ('describe it', 'describe')], attached=True)
        self.check([
            ('what is in the image?', 'describe'), ('thanks it looks great', 'chat'), ('tell me a joke', 'chat'),
            ('explain quantum computing', 'chat'), ('write a python script that sorts a list', 'chat'), ('nice', 'chat'),
            ('make a poem about it', 'chat'), ('how do I save it', 'chat'),
        ], recent=True)

    def test_ambiguous_turns_ask_the_model_and_fall_back_sensibly(self):
        self.assertEqual(image_turn_intent('a red sports car on a mountain road at dusk', recent=True), 'unsure')
        self.assertEqual(image_turn_fallback('a red sports car on a mountain road at dusk', recent=True), 'generate')
        self.assertEqual(image_turn_fallback('the dog should look happier', recent=True), 'edit')
        self.assertEqual(image_turn_fallback('in watercolor', attached=True), 'describe')
        self.assertEqual(image_turn_fallback('write me a story', recent=True), 'chat')

    def test_model_answers_are_parsed_strictly(self):
        self.assertEqual(parse_image_turn('{"route":"generate_new_image"}'), 'generate')
        self.assertEqual(parse_image_turn('{"route":"edit_image"}'), 'edit')
        self.assertIsNone(parse_image_turn('{"route":"delete_everything"}'))
        self.assertIsNone(parse_image_turn('not json'))

    def test_classifier_never_loads_a_model(self):
        class Engine:
            runtime = None; cfg = {}
        self.assertIsNone(classify_image_turn(Engine(), 'a castle', False, '', threading.Event()))

    def test_selector_needs_an_image_for_crop_resize_upscale(self):
        self.assertNotIn(select_image_operation('a large scale battle, crop top, enhance the colors', has_image=False)[0],
                         (ImageOperation.CROP, ImageOperation.RESIZE, ImageOperation.UPSCALE))
        self.assertEqual(select_image_operation('Resize this photo to 1024x768', has_image=True)[0], ImageOperation.RESIZE)


if __name__ == '__main__':
    unittest.main()
