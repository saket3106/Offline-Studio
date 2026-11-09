"""Single-coordinator checkpoints; recovery never executes an operation."""
import argparse
import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def file_hash(path):
    path = Path(path)
    if not path.exists():
        return None
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def source_path(root, relative):
    root = Path(root).resolve(strict=True)
    candidate = Path(relative)
    if candidate.is_absolute() or '..' in candidate.parts:
        raise ValueError('Expected a source-relative path')
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root) or resolved == root:
        raise ValueError('Path escapes canonical source')
    return resolved


def identities(root, paths):
    return {relative: file_hash(source_path(root, relative)) for relative in paths}


def validate(state):
    required = ('objective', 'backlog', 'completed', 'pending', 'ownership',
                'source_root', 'source_revision', 'files', 'tests', 'blockers',
                'routes', 'dependencies', 'next_action', 'usage')
    if any(field not in state for field in required):
        raise ValueError('Incomplete engineering checkpoint')
    if state.get('schema_version') != 1:
        raise ValueError('Unsupported checkpoint schema')
    if not isinstance(state['ownership'], dict) or not isinstance(state['files'], dict):
        raise ValueError('Invalid ownership or file identity map')
    root = Path(state['source_root']).resolve(strict=True)
    for relative in set(state['files']) | set(state['ownership']):
        source_path(root, relative)
    if set(state['ownership']) - set(state['files']):
        raise ValueError('Owned files require checkpoint identities')


def save(path, state, expected_revision):
    validate(state)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + '.lock')
    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temporary = None
    try:
        with os.fdopen(descriptor, 'w') as stream:
            stream.write(str(os.getpid()))
        current = json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        revision = current['revision'] if current else 0
        if revision != expected_revision:
            raise ValueError('Checkpoint changed; re-read before saving')
        saved = dict(state, revision=revision + 1,
                     updated_at=datetime.now(timezone.utc).isoformat())
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', suffix='.tmp', delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(saved, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        return saved
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)


def recover(path, root):
    state = json.loads(Path(path).read_text(encoding='utf-8'))
    validate(state)
    root = Path(root).resolve(strict=True)
    if root != Path(state['source_root']).resolve(strict=True):
        raise ValueError('Checkpoint belongs to another source tree')
    current = identities(root, state['files'])
    changed = [relative for relative, digest in current.items() if digest != state['files'][relative]]
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=root,
                              capture_output=True, text=True, timeout=10)
    revision_matches = revision.returncode == 0 and revision.stdout.strip() == state['source_revision']
    return {'revision': state['revision'], 'changed_files': changed,
            'source_revision_matches': revision_matches,
            'ownership_requires_review': state['ownership'],
            'status': 'REVIEW_REQUIRED' if changed or state['ownership'] or not revision_matches else 'READY',
            'next_action': state['next_action'], 'actions_executed': 0}


def select_fallback(routes, attempted, required_capability, max_attempts=2):
    if len(attempted) >= max_attempts:
        return None
    for route in routes:
        if (route['id'] not in attempted and route.get('authorized') is True
                and route.get('status') == 'verified'
                and required_capability in route.get('capabilities', [])):
            return route['id']
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkpoint', type=Path)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    arguments = parser.parse_args()
    result = recover(arguments.checkpoint, arguments.root)
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'READY' else 2


if __name__ == '__main__':
    raise SystemExit(main())
