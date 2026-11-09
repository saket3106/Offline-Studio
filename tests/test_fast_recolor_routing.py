import os
import sys
import time
import unittest
from pathlib import Path
from PIL import Image
import numpy as np

# Ensure source is on path
SOURCE_DIR = Path(__file__).resolve().parent.parent
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from image_pipeline import select_image_operation, ImageOperation, recolor_intent
from workspace_services import basic_image_edit
from app import find_available_conversation_image


class TestFastRecolorRouting(unittest.TestCase):

    def test_mustang_user_prompt_routing(self):
        """Verify the user's exact Mustang prompt routes to FAST_RECOLOR with zero model calls."""
        prompt = (
            "Change only the black exterior body paint of this Mustang to glossy metallic red. "
            "Do not regenerate the scene. Preserve headlights, windows, grille, tires, wheels, "
            "wet road, buildings, lighting and camera perspective. Use Fast Recolor when reliable. "
            "If automatic masking is inaccurate, request mask correction rather than silently using a full generative edit."
        )
        t0 = time.perf_counter()
        op, opts = select_image_operation(prompt, has_image=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        self.assertEqual(op, ImageOperation.FAST_RECOLOR)
        self.assertEqual(opts.get("color"), "#ca151c")
        self.assertEqual(opts.get("finish"), "metallic")
        self.assertEqual(opts.get("from_color"), "black")
        self.assertLess(elapsed_ms, 50.0, f"Route classification took too long: {elapsed_ms} ms")

    def test_all_six_structured_operations(self):
        """Verify selector accurately classifies all 6 operations."""
        cases = [
            ("Generate a stunning photograph of a red Ferrari in Paris", False, ImageOperation.TEXT_TO_IMAGE),
            ("Add a carbon fiber spoiler to the rear using generative edit", True, ImageOperation.GENERATIVE_IMAGE_EDIT),
            ("Change the black paint of this car to blue", True, ImageOperation.FAST_RECOLOR),
            ("Upscale this image to 4k with super-resolution", True, ImageOperation.UPSCALE),
            ("Resize this photo to 1024x768", True, ImageOperation.RESIZE),
            ("Crop the borders of this image", True, ImageOperation.CROP),
        ]
        for prompt, has_image, expected in cases:
            op, _ = select_image_operation(prompt, has_image=has_image)
            self.assertEqual(op, expected, f"Prompt '{prompt}' classified as {op}, expected {expected}")

    @unittest.skipUnless((SOURCE_DIR / "logs" / "speech-image-repair" / "mustang-original.png").is_file(),
                         "private Mustang photo fixture is not on this machine")
    def test_recolor_quality_and_pixel_preservation(self):
        """Execute Fast Recolor on the Mustang image and mathematically verify pixel preservation."""
        mustang_path = SOURCE_DIR / "logs" / "speech-image-repair" / "mustang-original.png"
        self.assertTrue(mustang_path.is_file(), "Mustang test image not found")

        out_dir = SOURCE_DIR / "logs" / "speech-image-repair" / "fast_recolor_verified"
        out_dir.mkdir(parents=True, exist_ok=True)

        opts = {
            "color": "#ca151c",
            "finish": "metallic",
            "from_color": "black",
            "auto_mask": True,
            "source_path": str(mustang_path),
            "path": str(mustang_path),
        }

        t_start = time.perf_counter()
        result = basic_image_edit(str(mustang_path), "recolor", opts, out_dir)
        total_ms = (time.perf_counter() - t_start) * 1000

        # Timing assertions: must be fast (< 3000 ms)
        self.assertLess(total_ms, 3000.0, f"Recolor was not fast: took {total_ms} ms")

        # Result checks
        self.assertTrue(Path(result["path"]).is_file())
        self.assertTrue(Path(result["maskPath"]).is_file())
        metrics = result["metrics"]
        self.assertEqual(metrics["modelCalls"], 0, "Fast Recolor must not invoke models")
        self.assertFalse(metrics["geometryResampled"], "Geometry must not be resampled")
        self.assertEqual(metrics["outsideMaskChangedPixels"], 0, "Pixels outside mask must be identical")

        # Numerical comparison
        orig = np.asarray(Image.open(mustang_path).convert("RGB"), dtype=np.float32)
        recol = np.asarray(Image.open(result["path"]).convert("RGB"), dtype=np.float32)
        mask = np.asarray(Image.open(result["maskPath"]).convert("L")) > 0

        # Dimensions check
        self.assertEqual(orig.shape, recol.shape, "Dimensions altered")

        # Outside mask strictly identical
        diff = np.abs(orig - recol)
        max_outside_diff = float(np.max(diff[~mask]))
        self.assertEqual(max_outside_diff, 0.0, f"Pixels outside mask changed by max {max_outside_diff}")

        # Inside mask changed to red
        red_increase = float(np.mean(recol[..., 0][mask] - orig[..., 0][mask]))
        self.assertGreater(red_increase, 25.0, "Body paint did not increase in red channel")
        # Clipped exclusion boundaries intentionally leave white reflections
        # untouched. Saturating a white highlight is not proof of paint quality.
        self.assertGreater(float(np.mean(recol[...,0][mask])),float(np.mean(recol[...,1][mask])),"Selected paint did not become predominantly red")
        self.assertTrue(metrics['maskRequiresReview'],"Heuristic coverage must not certify object accuracy")

    def test_conversation_image_resolution(self):
        """Verify find_available_conversation_image resolves prior images when no attachment is passed."""
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            mustang_path = str((Path(folder) / "mustang-original.png").resolve())
            Image.new("RGB", (64, 32), (10, 10, 10)).save(mustang_path)
            dummy_rows = [
                ("user", "Generate an image of a black Mustang", ""),
                ("assistant", "Finished: generate image", mustang_path),
            ]
            found = find_available_conversation_image(dummy_rows, "Change the paint to red")
            self.assertEqual(found.casefold(), mustang_path.casefold())


if __name__ == "__main__":
    unittest.main()
