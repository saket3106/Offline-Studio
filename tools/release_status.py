"""Read-only release evidence reconciliation. Never builds, launches or installs."""
from pathlib import Path
import argparse
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from in_place_packaging import digest, manifest_inputs, installed_executable


def report(project, journal_path, *, source_acceptance=None, native_acceptance=None, owner_acceptance=None):
    project = Path(project).resolve()
    source = project / 'Source'
    journal_path = Path(journal_path)
    journal = json.loads(journal_path.read_text(encoding='utf-8'))
    exe_path = installed_executable(project / 'Application')
    exe_hash = digest(exe_path)
    manifest_hash = digest(source / 'SOURCE_MANIFEST.sha256')
    source_error = None
    try:
        entries = manifest_inputs(source)
    except (OSError, ValueError) as exc:
        entries = None
        source_error = str(exc)
    installed = (journal.get('installed') is True and journal.get('newExeSha256') == exe_hash)
    current_source_installed = (installed and entries is not None
                                and journal.get('approvedSourceManifestSha256') == manifest_hash
                                and journal.get('sourceEntries') == entries)

    def acceptance(path, *, source_bound=False, status='PASS', scope=None):
        if path is None: return {'established': False, 'reason': 'No explicit acceptance receipt supplied'}
        path = Path(path)
        data = json.loads(path.read_text(encoding='utf-8'))
        bound = (entries is not None and data.get('sourceManifestSha256') == manifest_hash) if source_bound else data.get('exeSha256') == exe_hash
        valid = (data.get('status') == status and bound and (scope is None or data.get('scope') == scope))
        return {'established': bool(valid), 'path': str(path), 'sha256': digest(path),
                'reason': 'Matching recorded acceptance' if valid else 'Status, scope or identity does not match current inputs'}

    startup_count = journal.get('installedStartupChecks')
    mcp_count = journal.get('installedMCPChecks')
    verification = journal.get('independentVerification')
    startup_recorded = (installed and isinstance(verification, dict) and verification.get('status') == 'PASS'
                        and type(startup_count) is int and startup_count > 0
                        and type(mcp_count) is int and mcp_count > 0)
    return {
        'scope': 'Read-only identity reconciliation of recorded evidence; no acceptance workload executed',
        'installedExePath': str(exe_path),
        'installedExeSha256': exe_hash,
        'sourceManifestSha256': manifest_hash,
        'journal': {'path': str(journal_path), 'sha256': digest(journal_path), 'status': journal.get('status')},
        'implemented': {'sourceManifestVerified': entries is not None, 'manifestEntries': len(entries) if entries is not None else None, 'error': source_error},
        'tested': acceptance(source_acceptance, source_bound=True, scope='source'),
        'nativeVerified': acceptance(native_acceptance, source_bound=True, scope='native'),
        'installed': {'exeMatchesJournal': installed, 'currentSourceInstalled': current_source_installed,
                      'recordedStartupAccepted': bool(startup_recorded),
                      'recordedStartupChecks': startup_count, 'recordedMCPChecks': mcp_count},
        'ownerAccepted': acceptance(owner_acceptance, status='OWNER_ACCEPTED'),
        'notes': ['Source tests and packaged tool tests do not prove native model or microphone acceptance.',
                  'Historical reports are retained; identities take precedence over their prose.'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--journal', type=Path, required=True)
    for name in ['source-acceptance', 'native-acceptance', 'owner-acceptance']:
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    result = report(args.project, args.journal, source_acceptance=args.source_acceptance,
                    native_acceptance=args.native_acceptance, owner_acceptance=args.owner_acceptance)
    print(json.dumps(result, indent=2))
    return 0 if result['implemented']['sourceManifestVerified'] and result['installed']['exeMatchesJournal'] else 2


if __name__ == '__main__': sys.exit(main())
