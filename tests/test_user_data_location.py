"""The installed app keeps user data in UserData next to Application, only when that folder exists."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import integrated_runtime as runtime  # noqa: E402


class UserDataLocationTests(unittest.TestCase):
    def run_with(self, *, frozen, make_shared, env=None):
        with tempfile.TemporaryDirectory() as folder:
            app = Path(folder) / "Application"; app.mkdir()
            if make_shared:
                (Path(folder) / "UserData").mkdir()
            environ = {k: v for k, v in os.environ.items() if k != "OFFLINE_GPT_DATA_DIR"}
            if env:
                environ["OFFLINE_GPT_DATA_DIR"] = env
            with patch.object(runtime, "APP_DIR", app), patch.dict(os.environ, environ, clear=True), \
                    patch.object(sys, "frozen", frozen, create=True):
                return runtime.default_data_dir(), app

    def test_installed_app_uses_user_data_folder(self):
        found, app = self.run_with(frozen=True, make_shared=True)
        self.assertEqual(found, app.parent / "UserData")

    def test_installed_app_without_user_data_keeps_old_layout(self):
        found, app = self.run_with(frozen=True, make_shared=False)
        self.assertEqual(found, app)

    def test_source_runs_and_tests_never_use_real_user_data(self):
        found, app = self.run_with(frozen=False, make_shared=True)
        self.assertEqual(found, app)

    def test_environment_variable_wins(self):
        found, _ = self.run_with(frozen=True, make_shared=True, env=r"D:\Elsewhere")
        self.assertEqual(found, Path(r"D:\Elsewhere"))


if __name__ == "__main__":
    unittest.main()
