import unittest

from app import flux_step_distilled, parse_image_resolution_intent

DISTILLED = {'flux_model': 'flux-2-klein-9b-Q4_K_M.gguf'}
BASE = {'flux_model': 'flux-2-klein-base-9b-Q4_K_M.gguf'}


def native(prompt, cfg):
    r = parse_image_resolution_intent(prompt, dict(cfg))
    return (r['native_width'], r['native_height']), (r['target_width'], r['target_height'])


class FluxDistilledTests(unittest.TestCase):
    def test_distilled_klein_is_recognised(self):
        self.assertTrue(flux_step_distilled(r"C:\Models\Image\flux-2-klein-9b-Q4_K_M.gguf"))
        self.assertTrue(flux_step_distilled("FLUX.2-Klein-4B-Q8_0.gguf"))

    def test_base_and_other_models_keep_their_settings(self):
        self.assertFalse(flux_step_distilled(r"C:\Models\Image\flux-2-klein-base-9b-Q4_K_M.gguf"))
        self.assertFalse(flux_step_distilled("flux1-dev-Q4_K_S.gguf"))
        self.assertFalse(flux_step_distilled(None))

    def test_distilled_renders_large_targets_natively_at_2k(self):
        self.assertEqual(native('generate a 4k porsche wallpaper', DISTILLED), ((1920, 1088), (3840, 2160)))
        self.assertEqual(native('a 4k portrait of a lion', DISTILLED), ((1088, 1920), (2160, 3840)))
        self.assertEqual(native('2k mountain landscape', DISTILLED), ((1920, 1088), (2560, 1440)))
        self.assertEqual(native('1080p city at night', DISTILLED), ((1920, 1088), (1920, 1080)))

    def test_base_model_and_plain_requests_keep_their_sizes(self):
        self.assertEqual(native('generate a 4k porsche wallpaper', BASE), ((1024, 576), (3840, 2160)))
        self.assertEqual(native('1080p city at night', BASE), ((1024, 576), (1920, 1080)))
        self.assertEqual(native('a cat', DISTILLED), native('a cat', BASE))


if __name__ == "__main__":
    unittest.main()
