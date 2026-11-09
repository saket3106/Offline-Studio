"""Helper servers never outlive the app.

Measured 2026-11-07: a force-closed instance left llama-server (9B) and two whisper-server processes
running with dead parents; they held the GPU, so the next launch transcribed every spoken turn on the
CPU in ~12 s. These tests use real Windows processes (a copy of ping.exe stands in for a helper).
"""
import os, shutil, subprocess, sys, tempfile, time, unittest
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from integrated_runtime import stop_orphaned_helpers, tie_child_to_app

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def alive(pid):
    out = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'], capture_output=True, text=True, creationflags=NO_WINDOW).stdout
    return str(pid) in out


def wait_gone(pid, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if not alive(pid):
            return True
        time.sleep(0.2)
    return False


@unittest.skipUnless(os.name == 'nt', 'Windows job objects')
class HelperGuardTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.helper = self.folder / 'bin' / 'orphan-helper.exe'
        self.helper.parent.mkdir()
        shutil.copy(Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'PING.EXE', self.helper)
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            subprocess.run(['taskkill', '/F', '/PID', str(pid)], capture_output=True, creationflags=NO_WINDOW)
        for pid in self.pids:
            wait_gone(pid, 5)
        shutil.rmtree(self.folder, ignore_errors=True)

    def orphan(self, tie=False):
        """Start the helper from a short-lived parent process and return the helper's PID."""
        script = ("import subprocess,sys;sys.path.insert(0,sys.argv[2]);from integrated_runtime import tie_child_to_app\n"
                  "p=subprocess.Popen([sys.argv[1],'-n','60','127.0.0.1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)\n"
                  "print(p.pid, tie_child_to_app(p) if sys.argv[3]=='1' else False, flush=True)\n"
                  "import time;time.sleep(1.5)  # let the helper finish starting before its parent exits")
        # The venv's python.exe is a redirector that puts its children in its own kill-on-close job, which
        # would end the helper for the wrong reason; run the parent on the base interpreter instead.
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(path for path in sys.path if path))
        parent = getattr(sys, '_base_executable', sys.executable) or sys.executable
        out = subprocess.run([parent, '-B', '-c', script, str(self.helper), str(Path(__file__).resolve().parents[1]), '1' if tie else '0'],
                             capture_output=True, text=True, timeout=60, env=env, creationflags=NO_WINDOW)
        pid, tied = out.stdout.split()[:2]
        self.pids.append(int(pid))
        return int(pid), tied == 'True'

    def test_tied_helper_dies_with_its_app(self):
        pid, tied = self.orphan(tie=False)
        self.assertTrue(alive(pid), 'control: an untied helper survives its parent')
        stop_orphaned_helpers(self.folder, names=('orphan-helper.exe',))
        pid, tied = self.orphan(tie=True)
        self.assertTrue(tied)
        self.assertTrue(wait_gone(pid), 'kill-on-close job ends the helper when the app process exits')

    def test_untied_orphan_from_this_folder_is_stopped(self):
        pid, _ = self.orphan(tie=False)
        self.assertTrue(alive(pid))
        self.assertEqual(stop_orphaned_helpers(self.folder, names=('orphan-helper.exe',)), [pid])
        self.assertTrue(wait_gone(pid))

    def test_helper_with_live_parent_or_other_folder_is_kept(self):
        live = subprocess.Popen([str(self.helper), '-n', '60', '127.0.0.1'], stdout=subprocess.DEVNULL, creationflags=NO_WINDOW)
        self.pids.append(live.pid)
        pid, _ = self.orphan(tie=False)
        elsewhere = Path(tempfile.mkdtemp())
        try:
            self.assertEqual(stop_orphaned_helpers(elsewhere, names=('orphan-helper.exe',)), [], 'only helpers from the app folder')
        finally:
            shutil.rmtree(elsewhere, ignore_errors=True)
        self.assertEqual(stop_orphaned_helpers(self.folder, names=('orphan-helper.exe',)), [pid])
        self.assertTrue(alive(live.pid), 'a helper whose app is still running is kept')
        live.kill(); live.wait(5)

    def test_tie_is_safe_without_a_process(self):
        self.assertFalse(tie_child_to_app(None))


if __name__ == '__main__':
    unittest.main()
