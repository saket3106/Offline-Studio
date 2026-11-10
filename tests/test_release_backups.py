"""Updates keep only the newest backup sets, outside Application."""
import importlib.util
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

TOOL = Path(__file__).resolve().parents[1] / 'tools' / 'release_inplace.py'
spec = importlib.util.spec_from_file_location('release_inplace', TOOL)
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class UpdateBackupTests(unittest.TestCase):
    def test_only_the_newest_two_sets_survive(self):
        with tempfile.TemporaryDirectory() as folder:
            backups = Path(folder)
            now = time.time()
            for age, tag in enumerate(['Route-3', 'Route-2', 'Route-1']):
                for name in (f'Offline Studio.exe.bak-pre-{tag}', f'ui-pre-{tag}.zip', f'offline_gpt-pre-{tag}.sqlite3'):
                    (backups / name).write_text('x'); os.utime(backups / name, (now - age * 60, now - age * 60))
            with patch.object(release, 'UPDATE_BACKUPS', backups):
                release.prune_update_backups()
            left = sorted(p.name for p in backups.iterdir())
            self.assertEqual(len(left), 6)
            self.assertFalse(any('Route-1' in n for n in left))

    def test_backups_live_outside_the_application_folder(self):
        self.assertNotEqual(release.UPDATE_BACKUPS.parent.parent, release.APP)
        self.assertFalse(release.UPDATE_BACKUPS.is_relative_to(release.APP))


if __name__ == '__main__':
    unittest.main()
