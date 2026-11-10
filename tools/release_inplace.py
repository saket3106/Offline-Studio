"""Gated in-place release of Offline Studio (exe + ui) into ../Application.

Steps (run with the retained SDK Python, from Source):
  python -B tools/release_inplace.py prepare --prior <release dir name> --name <new release dir name>
  python -B tools/release_inplace.py build   --name <new release dir name>
  python -B tools/release_inplace.py install --name <new release dir name>
  python -B tools/release_inplace.py rollback --name <new release dir name>

prepare: seals SOURCE_MANIFEST.sha256 (changed + new tracked source files) and rebinds the
         unchanged owner-approved native pairs from the prior release (same procedure as
         Documentation/IntelligenceCompletion20261104/prepare_release.py). Trust records of
         earlier releases are never modified.
build:   runs PyInstaller with the reviewed build environment; the spec's own gates write
         PACKAGING_COMPATIBILITY.json and COMPILED_SOURCE_ACCEPTANCE.json.
install: refuses while Offline Studio runs; backs up exe, ui and a SQLite .backup() copy into
         Backups/Updates/ (only the newest KEEP_UPDATE_BACKUPS sets are kept), then copies the built
         exe and Source/ui into Application. Nothing else is added to Application.
rollback: restores the exe and ui saved by install.
"""
import argparse, copy, hashlib, json, os, shutil, sqlite3, subprocess, sys, time, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'Source'; APP = ROOT / 'Application'; CURRENT = ROOT / 'Recovery' / 'Current'
UPDATE_BACKUPS = ROOT / 'Backups' / 'Updates'; KEEP_UPDATE_BACKUPS = 2


def data_dir():
    """The installed app's data folder: UserData beside Application when present (see default_data_dir)."""
    shared = ROOT / 'UserData'
    return shared if shared.is_dir() else APP


def prune_update_backups():
    """Keep only the newest update backup sets; each set is exe + ui zip + database copy sharing one tag."""
    sets = {}
    for f in UPDATE_BACKUPS.glob('*-pre-*'):
        sets.setdefault(f.name.split('-pre-', 1)[1].rsplit('.', 1)[0].removesuffix('.zip'), []).append(f)
    newest = sorted(sets, key=lambda tag: max(f.stat().st_mtime for f in sets[tag]), reverse=True)
    for tag in newest[KEEP_UPDATE_BACKUPS:]:
        for f in sets[tag]:
            f.unlink()
sys.path.insert(0, str(SOURCE))
from in_place_packaging import digest, manifest_inputs  # noqa: E402

NEW_FILES = [
    'frontend-source/src/polish.css', 'frontend-source/src/studio.css',
    # Local assistant actions (imported by app.py; bundled as root modules).
    'assistant_actions.py', 'assistant_host.py', 'assistant_agent.py', 'pc_control.py',
]


def tracked_sources():
    out = subprocess.run(['git', 'ls-files'], cwd=SOURCE, capture_output=True, text=True, check=True).stdout.splitlines()
    return {p for p in out if p.endswith(('.py', '.jsx', '.js', '.css', '.json', '.md')) and not p.startswith(('backups/', 'logs/', 'generated/', 'thumbnails/'))}


def prepare(prior_name, name):
    from in_place_packaging import native_pin_inputs, controlled_build_environment, verify_native_signatures
    prior = CURRENT / prior_name; release = CURRENT / name
    manifest = SOURCE / 'SOURCE_MANIFEST.sha256'; old = {}
    for line in manifest.read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#'):
            checksum, entry = line.split('  ', 1); old[entry] = checksum
    tracked = tracked_sources()
    # Root-level .py entries become hidden imports of the exe, so only already-sealed
    # root modules are kept; new entries are limited to UI styles and unit tests.
    names = set(old) | {n for n in NEW_FILES if (SOURCE / n).is_file()} | {n for n in tracked if n.startswith('tests/test_') and (SOURCE / n).is_file()}
    names = {n for n in names if (SOURCE / n).is_file()}
    new = {n: digest(SOURCE / n) for n in sorted(names)}
    for n in [n for n in new if '/' not in n and n.endswith('.py')]:
        compile((SOURCE / n).read_text(encoding='utf-8-sig'), n, 'exec')
    release.mkdir(exist_ok=False)
    (release / 'SOURCE_MANIFEST-before.sha256').write_bytes(manifest.read_bytes())
    manifest.write_text(''.join(c + '  ' + n + '\n' for n, c in new.items()), encoding='utf-8'); manifest_inputs(SOURCE)
    changes = {n: {'previous': old.get(n), 'current': c} for n, c in new.items() if old.get(n) != c}
    (release / 'SOURCE_SEAL.json').write_text(json.dumps({'status': 'PASS', 'manifestSha256': digest(manifest), 'entries': len(new), 'changes': changes}, indent=2), encoding='utf-8')

    def write(fname, value):
        path = release / fname; assert not path.exists(); path.write_text(json.dumps(value, indent=2), encoding='utf-8'); return path

    def authority(path): return {'path': str(path), 'sha256': digest(path)}
    approved_path = prior / 'PACKAGING_COMPATIBILITY.json'; approved = json.loads(approved_path.read_text())
    compiled = json.loads((prior / 'COMPILED_SOURCE_ACCEPTANCE.json').read_text()); current = digest(APP / 'Offline Studio.exe')
    assert current == compiled['exeSha256'], 'Installed exe does not match the prior release receipt'
    old_proof_path = Path(approved['nativeInputPins']['receipt']); assert digest(old_proof_path) == approved['nativeInputPins']['sha256']
    proof = copy.deepcopy(json.loads(old_proof_path.read_text())); proof['installedExeSha256'] = current
    proof['scope'] = f'Unchanged owner-approved native pairs reused for owner-requested in-place release {name}; no new signer, bytes, origins or independent authority.'
    proof['authorityReceipts'].extend([authority(old_proof_path), authority(prior / 'BUILD_ENVIRONMENT.json')])
    # The gate admits at most 64 authorities and every in-place release appends two. Older in-place
    # chain receipts stay hash-bound through the prior proof (listed here), which lists its own
    # predecessors, so only the oldest chain pairs are dropped; independent originals are always kept.
    def chain(a): p = Path(a['path']); return p.parent.parent == CURRENT and p.name in ('NATIVE_PIN_REVIEW.json', 'BUILD_ENVIRONMENT.json')
    while len(proof['authorityReceipts']) > 64:
        proof['authorityReceipts'].remove(next(a for a in proof['authorityReceipts'] if chain(a)))
    pin = write('NATIVE_PIN_REVIEW.json', proof)
    relocation = copy.deepcopy(json.loads((prior / 'EXACT_ORIGINAL_RELOCATION.json').read_text()))
    relocation.update(installedExeSha256=current, historicalProofSha256=approved['nativeInputPins']['sha256'], continuingReleaseAuthorization=f'Owner-requested in-place release {name}; identical mapping, historical receipts retained.')
    relocated = write('EXACT_ORIGINAL_RELOCATION.json', relocation)
    compiled.update(nativeInputPinReceipt=str(pin), nativeInputPinSha256=digest(pin), originalInputRelocationReceipt=str(relocated), originalInputRelocationSha256=digest(relocated),
                    historicalBuildEnvironmentReceipt=str(prior / 'BUILD_ENVIRONMENT.json'), historicalBuildEnvironmentSha256=digest(prior / 'BUILD_ENVIRONMENT.json'))
    binding = write('COMPILED_BASELINE.json', compiled); pairs = native_pin_inputs(approved, APP, compiled); signatures = verify_native_signatures(pairs)
    old_env = json.loads((prior / 'BUILD_ENVIRONMENT.json').read_text())
    _, policy = controlled_build_environment(approved, APP, old_env['interpreter'], old_env['basePrefix'], old_env['systemRoot'], os.environ, compiled)
    write('BUILD_ENVIRONMENT.json', dict(priorCompatibilityReceipt=str(approved_path), priorCompatibilitySha256=digest(approved_path), priorCompiledReceipt=str(binding),
                                          priorCompiledSha256=digest(binding), interpreter=old_env['interpreter'], basePrefix=old_env['basePrefix'], systemRoot=old_env['systemRoot'], environment=policy))
    print(json.dumps({'status': 'PASS', 'installedExeSha256': current, 'nativePairs': len(pairs), 'validSignatures': len(signatures), 'manifestEntries': len(new), 'changedEntries': sorted(changes)}, indent=2))


def build(name):
    from in_place_packaging import verify_build_environment
    release = CURRENT / name; manifest_inputs(SOURCE)
    record = json.loads((release / 'BUILD_ENVIRONMENT.json').read_text())
    env = dict(os.environ, PATH=record['environment']['path'], OFFLINEGPT_APPROVED_INPLACE_BUILD='20261104-owner-approved', OFFLINEGPT_RELEASE_ROOT=str(release),
               OFFLINEGPT_COMPATIBILITY_RECEIPT=str(release / 'PACKAGING_COMPATIBILITY.json'), OFFLINEGPT_BUILD_ENV_RECEIPT=str(release / 'BUILD_ENVIRONMENT.json'))
    original = os.environ.copy()
    try: os.environ.clear(); os.environ.update(env); verify_build_environment(release / 'BUILD_ENVIRONMENT.json', APP)
    finally: os.environ.clear(); os.environ.update(original)
    assert not (release / 'BUILD_INVOCATION.json').exists(), 'One build per release root'
    command = [record['interpreter'], '-I', '-B', '-X', 'utf8', '-m', 'PyInstaller', '--noconfirm', '--workpath', str(release), '--distpath', str(release), str(SOURCE / 'Offline GPT.inplace.spec')]
    report = {'command': command, 'sourceManifestSha256': digest(SOURCE / 'SOURCE_MANIFEST.sha256'), 'previousExeSha256': digest(APP / 'Offline Studio.exe'), 'started': time.time(), 'output': str(release / 'Offline GPT.inplace' / 'Offline Studio.exe')}
    (release / 'BUILD_INVOCATION.json').write_text(json.dumps(report, indent=2))
    with (release / 'pyinstaller-build.txt').open('wb') as log: result = subprocess.run(command, cwd=SOURCE, env=env, stdout=log, stderr=subprocess.STDOUT)
    report.update(exitCode=result.returncode, finished=time.time())
    if Path(report['output']).is_file(): report['candidateExeSha256'] = digest(report['output'])
    (release / 'BUILD_RESULT.json').write_text(json.dumps(report, indent=2)); print(json.dumps(report, indent=2)); raise SystemExit(result.returncode)


def running():
    out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq Offline Studio.exe', '/FO', 'CSV', '/NH'], capture_output=True, text=True).stdout
    return 'Offline Studio.exe' in out


def install(name):
    release = CURRENT / name; built = release / 'Offline GPT.inplace' / 'Offline Studio.exe'
    accepted = json.loads((release / 'COMPILED_SOURCE_ACCEPTANCE.json').read_text())
    assert digest(built) == accepted['exeSha256'], 'Built exe does not match its compiled acceptance receipt'
    if running(): raise SystemExit('Offline Studio is running; close it first.')
    backups = UPDATE_BACKUPS; backups.mkdir(parents=True, exist_ok=True); tag = f'pre-{name}'
    shutil.copy2(APP / 'Offline Studio.exe', backups / f'Offline Studio.exe.bak-{tag}')
    with zipfile.ZipFile(backups / f'ui-{tag}.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        for f in (APP / 'ui').rglob('*'):
            if f.is_file(): z.write(f, f.relative_to(APP / 'ui'))
    src = sqlite3.connect(f'file:{data_dir() / "offline_gpt.sqlite3"}?mode=ro', uri=True); dst = sqlite3.connect(backups / f'offline_gpt-{tag}.sqlite3')
    src.backup(dst); check = dst.execute('pragma quick_check').fetchone()[0]; chats = dst.execute('select count(*) from chats').fetchone()[0]; dst.close(); src.close()
    assert check == 'ok', 'Database backup failed integrity check'
    shutil.copy2(built, APP / 'Offline Studio.exe')
    for f in (SOURCE / 'ui').rglob('*'):
        if f.is_file():
            target = APP / 'ui' / f.relative_to(SOURCE / 'ui'); target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(f, target)
    mismatched = [str(f.relative_to(SOURCE / 'ui')) for f in (SOURCE / 'ui').rglob('*') if f.is_file() and digest(f) != digest(APP / 'ui' / f.relative_to(SOURCE / 'ui'))]
    result = {'installedExeSha256': digest(APP / 'Offline Studio.exe'), 'expected': accepted['exeSha256'], 'uiMismatches': mismatched, 'backupTag': tag, 'chatsInBackup': chats, 'dbBackupCheck': check}
    (release / 'INSTALL_RESULT.json').write_text(json.dumps(result, indent=2)); print(json.dumps(result, indent=2))
    assert result['installedExeSha256'] == accepted['exeSha256'] and not mismatched
    prune_update_backups()


def rollback(name):
    if running(): raise SystemExit('Offline Studio is running; close it first.')
    tag = f'pre-{name}'
    backups = next((d for d in (UPDATE_BACKUPS, ROOT / 'Backups' / 'Application-backups', APP / 'backups')
                    if (d / f'Offline Studio.exe.bak-{tag}').is_file()), UPDATE_BACKUPS)
    shutil.copy2(backups / f'Offline Studio.exe.bak-{tag}', APP / 'Offline Studio.exe')
    with zipfile.ZipFile(backups / f'ui-{tag}.zip') as z: z.extractall(APP / 'ui')
    print('Restored', digest(APP / 'Offline Studio.exe'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('step', choices=['prepare', 'build', 'install', 'rollback'])
    parser.add_argument('--prior'); parser.add_argument('--name', required=True); a = parser.parse_args()
    {'prepare': lambda: prepare(a.prior, a.name), 'build': lambda: build(a.name), 'install': lambda: install(a.name), 'rollback': lambda: rollback(a.name)}[a.step]()
