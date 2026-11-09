"""Authoritative identity mismatches must never turn into installed/accepted claims."""
import json
import tempfile
import unittest
from pathlib import Path
from in_place_packaging import digest
from tools.release_status import report


class ReleaseStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.source = self.root/'Source'; self.app = self.root/'Application'
        self.source.mkdir(); self.app.mkdir()
        (self.source/'app.py').write_text('print("authored fixture")\n')
        (self.source/'SOURCE_MANIFEST.sha256').write_text(digest(self.source/'app.py')+'  app.py\n')
        (self.app/'Offline GPT.exe').write_bytes(b'authoritative executable fixture')
        (self.app/'offline_gpt.sqlite3').write_bytes(b'protected user data sentinel')
        self.journal = self.root/'UPDATE_JOURNAL.json'
        self.state = {'installed':True,'newExeSha256':digest(self.app/'Offline GPT.exe'),
                      'approvedSourceManifestSha256':digest(self.source/'SOURCE_MANIFEST.sha256'),
                      'sourceEntries':{'app.py':digest(self.source/'app.py')},
                      'independentVerification':{'status':'PASS'},'installedStartupChecks':23,'installedMCPChecks':12}
        self.save()

    def save(self): self.journal.write_text(json.dumps(self.state))
    def receipt(self, **values):
        path = self.root/'acceptance.json'; path.write_text(json.dumps(values)); return path

    def test_matching_install_never_invents_native_tests_or_owner_acceptance(self):
        before = {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        result = report(self.root, self.journal)
        self.assertTrue(result['installed']['currentSourceInstalled'])
        self.assertTrue(result['installed']['recordedStartupAccepted'])
        for key in ['tested','nativeVerified','ownerAccepted']: self.assertFalse(result[key]['established'])
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob('*') if p.is_file()})

    def test_changed_executable_invalidates_installed_and_owner_receipt(self):
        owner = self.receipt(status='OWNER_ACCEPTED', exeSha256=self.state['newExeSha256'])
        (self.app/'Offline GPT.exe').write_bytes(b'new unknown executable')
        result = report(self.root, self.journal, owner_acceptance=owner)
        self.assertFalse(result['installed']['exeMatchesJournal'])
        self.assertFalse(result['installed']['recordedStartupAccepted'])
        self.assertFalse(result['ownerAccepted']['established'])

    def test_renamed_main_executable_preserves_identity_reconciliation(self):
        (self.app/'Offline GPT.exe').rename(self.app/'Offline Studio.exe')
        result=report(self.root,self.journal)
        self.assertTrue(result['installed']['exeMatchesJournal'])
        self.assertEqual(result['installedExePath'],str(self.app/'Offline Studio.exe'))

    def test_source_drift_does_not_erase_verified_old_install(self):
        (self.source/'app.py').write_text('changed source')
        result = report(self.root, self.journal)
        self.assertFalse(result['implemented']['sourceManifestVerified'])
        self.assertTrue(result['installed']['exeMatchesJournal'])
        self.assertFalse(result['installed']['currentSourceInstalled'])

    def test_fresh_sealed_source_is_not_automatically_installed(self):
        (self.source/'app.py').write_text('changed source')
        (self.source/'SOURCE_MANIFEST.sha256').write_text(digest(self.source/'app.py')+'  app.py\n')
        result = report(self.root, self.journal)
        self.assertTrue(result['implemented']['sourceManifestVerified'])
        self.assertFalse(result['installed']['currentSourceInstalled'])

    def test_only_exact_scoped_source_receipt_establishes_tests(self):
        receipt = self.receipt(status='PASS', scope='source', sourceManifestSha256=self.state['approvedSourceManifestSha256'])
        result = report(self.root, self.journal, source_acceptance=receipt, native_acceptance=receipt)
        self.assertTrue(result['tested']['established']); self.assertFalse(result['nativeVerified']['established'])
        self.state['installedStartupChecks'] = True; self.save()
        self.assertFalse(report(self.root, self.journal)['installed']['recordedStartupAccepted'])

    def test_stale_source_acceptance_and_incomplete_journal_fail_closed(self):
        receipt = self.receipt(status='PASS', scope='source', sourceManifestSha256='0'*64)
        self.state.pop('independentVerification'); self.save()
        result = report(self.root, self.journal, source_acceptance=receipt)
        self.assertFalse(result['tested']['established']); self.assertFalse(result['installed']['recordedStartupAccepted'])


if __name__ == '__main__': unittest.main()
