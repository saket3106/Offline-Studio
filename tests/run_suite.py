"""Run every tests/test_*.py in its own process with a timeout; write a summary.

Usage: python -B tests/run_suite.py [summary_path]
Native/Qt acceptance scripts (qt_*.py, packaged_*.py, native_*) are not unit tests and are skipped.
"""
import os, re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'logs' / 'unit-suite-summary.txt'
out_path.parent.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, QT_QPA_PLATFORM='offscreen', PYTHONDONTWRITEBYTECODE='1')
rows = []; totals = {'ran': 0, 'failed': 0, 'errors': 0, 'timeouts': 0}
for test in sorted((ROOT / 'tests').glob('test_*.py')):
    started = time.time()
    try:
        proc = subprocess.run([sys.executable, '-B', '-m', 'unittest', f'tests.{test.stem}'], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=240, encoding='utf-8', errors='replace')
        text = proc.stdout + proc.stderr
        ran = int((re.search(r'Ran (\d+) test', text) or [0, 0])[1])
        fail = int((re.search(r'failures=(\d+)', text) or [0, 0])[1]); err = int((re.search(r'errors=(\d+)', text) or [0, 0])[1])
        status = 'OK' if proc.returncode == 0 else 'FAIL'
        names = re.findall(r'^(?:FAIL|ERROR): (\S+ \([^)]*\))', text, re.M)
    except subprocess.TimeoutExpired:
        ran, fail, err, status, names = 0, 0, 0, 'TIMEOUT', []
        totals['timeouts'] += 1
    totals['ran'] += ran; totals['failed'] += fail; totals['errors'] += err
    rows.append(f'{status:8} {test.stem:55} ran={ran:<4} fail={fail} err={err} {time.time()-started:5.1f}s ' + '; '.join(names[:6]))
    out_path.write_text('\n'.join(rows) + f'\n\nTOTAL {totals}\n', encoding='utf-8')
print(out_path.read_text(encoding='utf-8'))
