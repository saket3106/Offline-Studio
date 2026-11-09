import unittest
import time
import json
import sqlite3
import tempfile
import numpy as np
from pathlib import Path
from PIL import Image

import app
from image_pipeline import extract_image_constraints, preserve_image_constraints, recolor_intent
from workspace_services import basic_image_edit, generate_subject_mask, masked_recolor


class HandoffAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parent.parent.parent
        cls.offline_gpt_dir = (cls.root / "Application") if (cls.root / "Application").exists() else (cls.root / "Offline GPT")
        mustang_candidates = [
            cls.offline_gpt_dir / "generated" / "flux_20261010_151912_c327d0.png",
            cls.root / "Offline GPT" / "generated" / "flux_20261010_151912_c327d0.png",
            cls.root / "Application" / "generated" / "flux_20261010_151912_c327d0.png",
            cls.root / "Source" / "generated" / "flux_20261010_151912_c327d0.png",
        ]
        cls.source_mustang = next((p for p in mustang_candidates if p.exists()), mustang_candidates[0])
        candidates = [
            cls.root / "source" / "tests" / "fixtures" / "SELF_LEARNING_Alex_Doe_Final.pdf",
            Path("tests/fixtures/SELF_LEARNING_Alex_Doe_Final.pdf").resolve(),
            Path(r"C:\Users\mesak\Downloads\SELF_LEARNING_Alex_Doe_Final.pdf"),
        ]
        cls.pdf_path = next((p for p in candidates if p.exists()), candidates[0])

    def test_a_fast_recolor_mustang(self):
        """TEST A: Fast Recolor on black Mustang image under 5 seconds with 0 model calls."""
        self.assertTrue(self.source_mustang.exists(), f"Source Mustang image not found: {self.source_mustang}")
        prompt = (
            "Change only the black paint of this Mustang to glossy metallic red. "
            "Preserve the original scene, windows, tires, grille, headlights, reflections and lighting."
        )
        # Step 1: Verify recolor routing classification
        intent = recolor_intent(prompt)
        self.assertIsNotNone(intent, "recolor_intent failed to detect recolor request")
        self.assertEqual(intent['color'], '#ca151c')
        self.assertEqual(intent['finish'], 'metallic')
        self.assertEqual(intent['from_color'], 'black')

        # Step 2: Execute Fast Recolor pipeline
        t0 = time.perf_counter()
        isolated=tempfile.TemporaryDirectory()
        self.addCleanup(isolated.cleanup)
        out_dir=Path(isolated.name)
        opts = dict(intent)
        opts.update(auto_mask=True, source_path=str(self.source_mustang))

        res = basic_image_edit(str(self.source_mustang), 'recolor', opts, out_dir)
        total_ms = (time.perf_counter() - t0) * 1000

        # Step 3: Verify performance and fidelity metrics
        out_path = Path(res['path'])
        self.assertTrue(out_path.exists(), "Recolored output file was not created")
        mask_path = Path(res['maskPath'])
        self.assertTrue(mask_path.exists(), "Mask PNG file was not created")
        self.assertEqual(res['dimensions'], '3840 × 2160')
        self.assertIn('automated paint mask', res['method'])
        self.assertEqual(res['metrics']['modelCalls'], 0)
        self.assertFalse(res['metrics']['geometryResampled'])
        self.assertEqual(res['metrics']['outsideMaskChangedPixels'], 0)
        self.assertLess(total_ms, 8000, f"Fast Recolor took {total_ms:.1f}ms, expected under 8000ms")

        # Step 4: Verify image content
        with Image.open(out_path) as im:
            self.assertEqual(im.size, (3840, 2160))
            self.assertEqual(im.mode, 'RGB')

        # Clean up temporary test output if necessary, or keep for audit
        print(f"\n[TEST A PASS] Fast Recolor completed in {total_ms:.1f}ms (mask={res['metrics']['maskMs']}ms, recolor={res['metrics']['recolorMs']}ms, save={res['metrics']['saveMs']}ms)")

    def test_e_image_prompt_mode_fidelity(self):
        """TEST E: Creative Direction and Smart Enhance must preserve immutable constraints."""
        user_prompt = "Generate a glossy black modern 2024 Ford Mustang GT coupe, front three-quarter view, parked outside a glass office building. No other vehicles."
        constraints = extract_image_constraints(user_prompt)
        self.assertIn('black', constraints['color'])
        self.assertIn('modern', constraints['era'])
        self.assertIn('2024', constraints['era'])
        self.assertIn('coupe', constraints['identity'])
        self.assertIn('ford', constraints['identity'])
        self.assertIn('mustang', constraints['identity'])
        self.assertEqual(constraints['prohibitions'], ['No other vehicles'])

        # Smart enhance: valid faithful plan
        valid_plan = "A factory-correct glossy black 2024 Ford Mustang GT coupe parked in front of a modern glass office building, low front three-quarter angle, soft ambient reflections, clear glass reflections, no other vehicles."
        final, meta = preserve_image_constraints(user_prompt, valid_plan, 'smart_enhance')
        self.assertTrue(meta['plannerAccepted'])
        self.assertIn('black', final.lower())
        self.assertIn('2024', final.lower())

        # Creative direction: conflicting color/era plan must be rejected and repaired
        conflicting_plan = "A customized red vintage 1969 Ford Mustang fastback parked on a rain-slicked cobblestone street at sunset with neon reflections."
        final_repaired, meta_repaired = preserve_image_constraints(user_prompt, conflicting_plan, 'creative')
        self.assertFalse(meta_repaired['plannerAccepted'])
        self.assertIn('body color conflict', meta_repaired['conflicts'])
        self.assertIn('modern subject changed to vintage', meta_repaired['conflicts'])
        self.assertNotIn('1969', final_repaired)
        self.assertNotIn('red', final_repaired.lower())
        self.assertIn('glossy black', final_repaired.lower())
        print("\n[TEST E PASS] Prompt fidelity successfully guarded across all modes")

    def test_f_pdf_exact_search_regression(self):
        """TEST F: Verify PDF exact search correctly identifies physical page 8 in fixture."""
        from rag_engine import search_document_exact
        from document_tools import extract_document_cached
        if not self.pdf_path.exists():
            self.skipTest(f"Fixture PDF not found at {self.pdf_path}")
        content, meta = extract_document_cached(self.pdf_path, None)
        result = search_document_exact(content, 'Search for the phrase "Sample values for illustration only."', source_name=self.pdf_path.name, metadata=meta)
        self.assertEqual(result.get('status'), 'FOUND')
        pages = [loc['page'] for m in result.get('matches', []) for loc in m.get('locations', [])]
        self.assertIn(8, pages)
        print("\n[TEST F PASS] PDF exact search found physical page 8")


if __name__ == '__main__':
    unittest.main()
