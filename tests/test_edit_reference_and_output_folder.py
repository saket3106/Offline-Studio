"""Found in the real app 2026-11-12: editing a 4K result failed ("exceeds the 20 MB reference limit") and new images
were written into Application\\generated instead of UserData\\generated."""
import re
import tempfile
import unittest
from pathlib import Path

from PIL import Image

import reference_workflow as rw

SOURCE = Path(__file__).resolve().parents[1]


class WorkingReferenceTests(unittest.TestCase):
    def test_small_images_are_used_as_they_are(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'small.png'; Image.new('RGB', (1024, 768), 'red').save(src)
            self.assertEqual(rw.working_reference(src, Path(d) / 'cache'), src.resolve())

    def test_oversized_results_get_a_bounded_cached_copy(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'big.png'; Image.new('RGB', (3840, 2160), 'blue').save(src)
            original = rw.MAX_REFERENCE_BYTES
            rw.MAX_REFERENCE_BYTES = 1000  # the real 25 MB 4K PNG is over the limit; a flat test PNG is not
            try:
                first = rw.working_reference(src, Path(d) / 'cache')
                again = rw.working_reference(src, Path(d) / 'cache')
            finally:
                rw.MAX_REFERENCE_BYTES = original
            self.assertNotEqual(first, src.resolve())
            self.assertEqual(first, again)
            with Image.open(first) as copy:
                self.assertEqual(copy.size, (2048, 1152))
            rw._image(first)  # passes the same checks the native dispatch applies

    def test_large_dimensions_alone_are_scaled(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / 'wide.png'; Image.new('RGB', (4096, 1024), 'green').save(src)
            with Image.open(rw.working_reference(src, Path(d) / 'cache')) as copy:
                self.assertEqual(max(copy.size), 2048)


class OutputFolderTests(unittest.TestCase):
    def test_relative_image_folder_resolves_into_user_data(self):
        text = (SOURCE / 'app.py').read_text(encoding='utf-8')
        target = text[text.index('    def _target(self,cfg,prefix,extension=None):'):][:900]
        self.assertRegex(target, re.escape("(DATA_DIR/configured) if configured and not Path(configured).expanduser().is_absolute()"))


if __name__ == '__main__':
    unittest.main()
