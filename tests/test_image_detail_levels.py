import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from app import (FluxWorker, apply_image_detail_level, detail_tile_starts, image_detail_level,
                 normalize_detail_level, parse_image_resolution_intent)

FAST = {'flux_model': 'flux-2-klein-9b-Q4_K_M.gguf'}
BASE = {'flux_model': 'flux-2-klein-base-9b-Q4_K_M.gguf'}


def plan(prompt, level, model=FAST):
    cfg = dict(model, flux_detail_level=level)
    return apply_image_detail_level(parse_image_resolution_intent(prompt, cfg), prompt, cfg)


def sizes(p):
    return (p['native_width'], p['native_height']), (p['target_width'], p['target_height']), p['detail_refine']


class DetailLevelTests(unittest.TestCase):
    def test_levels_pick_output_size(self):
        self.assertEqual(sizes(plan('a red fox in snow', 'standard')), ((1024, 576), (1024, 576), False))
        self.assertEqual(sizes(plan('a red fox in snow', 'detailed')), ((1920, 1088), (1920, 1080), False))
        self.assertEqual(sizes(plan('a red fox in snow', 'high')), ((1920, 1088), (3840, 2160), False))
        self.assertEqual(sizes(plan('a red fox in snow', 'extreme')), ((1920, 1088), (3840, 2160), True))

    def test_shape_follows_prompt(self):
        self.assertEqual(sizes(plan('a portrait of a lion', 'high'))[1], (2160, 3840))
        self.assertEqual(sizes(plan('a square logo of a fox', 'extreme')), ((1440, 1440), (2160, 2160), True))

    def test_typed_size_wins(self):
        self.assertEqual(sizes(plan('a 1080p city', 'extreme')), ((1920, 1088), (1920, 1080), False))
        self.assertEqual(sizes(plan('a 1024x576 city', 'high'))[1], (1024, 576))
        self.assertTrue(plan('a 4k city', 'extreme')['detail_refine'])

    def test_prompt_words_raise_level_only_with_fast_model(self):
        self.assertEqual(image_detail_level('a fox, extremely detailed', dict(FAST)), 'extreme')
        self.assertEqual(image_detail_level('a highly detailed fox', dict(FAST)), 'high')
        self.assertEqual(image_detail_level('a highly detailed fox', dict(FAST, flux_detail_level='extreme')), 'extreme')
        self.assertEqual(image_detail_level('a highly detailed fox', dict(BASE)), 'standard')

    def test_base_model_never_runs_the_tiled_pass(self):
        self.assertFalse(plan('a red fox', 'extreme', BASE)['detail_refine'])

    def test_unknown_level_is_standard(self):
        self.assertEqual(normalize_detail_level('ULTRA'), 'standard')
        self.assertEqual(normalize_detail_level(' High '), 'high')

    def test_tiles_cover_with_overlap(self):
        self.assertEqual(detail_tile_starts(3840, 1408), [0, 1216, 2432])
        self.assertEqual(detail_tile_starts(2160, 1168), [0, 992])
        self.assertEqual(detail_tile_starts(1000, 1408), [0])


class RefineTilesTests(unittest.TestCase):
    def test_tiles_are_redrawn_and_blended_into_full_picture(self):
        folder = Path(tempfile.mkdtemp())
        try:
            source = folder / 'flux-sharp.png'
            Image.new('RGB', (3840, 2160), (40, 80, 120)).save(source)
            calls = []

            def fake_run(command, cli, label, stage_log=None, upscale=False, detail_label=None):
                calls.append((command, detail_label))
                tile_in = Path(command[command.index('-i') + 1])
                with Image.open(tile_in) as im:
                    Image.new('RGB', im.size, (200, 100, 50)).save(command[command.index('-o') + 1])

            worker = SimpleNamespace(cancel_event=threading.Event(), progress=SimpleNamespace(emit=lambda *_: None), _run_cli=fake_run)
            out = FluxWorker._refine_tiles(worker, source, lambda w, h: ['sd-cli', '-W', str(w), '-H', str(h), '-o', 'x.png'], Path('cli'), folder)
            self.assertEqual(len(calls), 6)
            self.assertIn('--strength', calls[0][0])
            self.assertEqual(calls[-1][1], 'Adding fine detail · part 6 of 6')
            with Image.open(out) as result:
                self.assertEqual(result.size, (3840, 2160))
                self.assertEqual(result.getpixel((1900, 1080)), (200, 100, 50))
            self.assertFalse((folder / 'flux-sharp-tiles').exists())
        finally:
            shutil.rmtree(folder, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
