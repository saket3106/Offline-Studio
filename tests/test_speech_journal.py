"""Speech lifecycle receipts must not rewrite completed operations."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
import app

class SpeechJournalTests(unittest.TestCase):
 def test_real_sqlite_success_survives_stop_next_playback_and_stale_callback(self):
  with tempfile.TemporaryDirectory() as folder,patch.object(app,'DB_PATH',Path(folder)/'synthetic.sqlite3'):
   store=app.Store();b=SimpleNamespace(backend=SimpleNamespace(store=store,voice_mode_active=False,busy=False),speech_operation=None,event=Mock())
   emit=lambda ident,state:app.DesktopBridge._speech_changed(b,{'operationId':ident,'state':state})
   try:
    emit('one','loading');emit('one','ready')
    first=store.con.execute('SELECT state,finished FROM operation_journal WHERE id=?',('one',)).fetchone()
    emit('','ready');emit('two','loading');emit('one','speaking');emit('one','ready')
    self.assertEqual(store.con.execute('SELECT state,finished FROM operation_journal WHERE id=?',('one',)).fetchone(),first)
    self.assertEqual(first[0],'success');self.assertEqual(b.speech_operation,'two')
    emit('two','ready');self.assertIsNone(b.speech_operation)
    self.assertEqual(store.con.execute('SELECT id,state FROM operation_journal ORDER BY id').fetchall(),[('one','success'),('two','success')])
   finally:store.con.close()
 def test_only_active_interrupted_operation_is_cancelled_once(self):
  workspace=Mock();b=SimpleNamespace(backend=SimpleNamespace(store=SimpleNamespace(workspace=workspace),voice_mode_active=False,busy=False),speech_operation=None,event=Mock())
  app.DesktopBridge._speech_changed(b,{'operationId':'active','state':'speaking'})
  app.DesktopBridge._speech_changed(b,{'operationId':'','state':'ready'})
  app.DesktopBridge._speech_changed(b,{'operationId':'','state':'ready'})
  workspace.finish.assert_called_once_with('active','cancelled')
  self.assertIsNone(b.speech_operation or None)

if __name__=='__main__':unittest.main()
