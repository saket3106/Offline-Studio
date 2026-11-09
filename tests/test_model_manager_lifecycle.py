"""Runtime/default distinction and model-reference safety; no native loading."""
import json,sqlite3,tempfile,threading,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from model_library import ModelLibrary
from integrated_runtime import EngineManager
try:
    from test_model_inspection import fixture
except ModuleNotFoundError:
    from tests.test_model_inspection import fixture
import app

class ReferenceSafety(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.con=sqlite3.connect(self.root/'test.sqlite3');self.addCleanup(self.con.close)
  self.con.execute('CREATE TABLE chats(id TEXT PRIMARY KEY, model_override TEXT)');self.con.commit()
  self.con.execute('CREATE TABLE messages(id INTEGER PRIMARY KEY, chat_id TEXT, role TEXT, content TEXT, created REAL)');self.con.commit()
  self.ws=SimpleNamespace(con=self.con,lock=threading.RLock(),directory=self.root)
  self.library=ModelLibrary(self.ws);self.file=self.root/'fixture.gguf'
  self.file.write_bytes(fixture([('general.architecture',8,'qwen3'),('general.name',8,'Metadata-only fixture'),('tokenizer.chat_template',8,'{{ messages }}')]))
  self.mid=self.library.import_file(str(self.file))['id']
 def test_conversation_references_cannot_be_orphaned(self):
  for ref in [self.mid,str(self.file),self.file.name,'Metadata-only fixture']:
   self.con.execute('INSERT OR REPLACE INTO chats VALUES(?,?)',('saved',ref));self.con.commit()
   with self.subTest(reference=ref),self.assertRaisesRegex(ValueError,'conversation uses'):self.library.remove_reference(self.mid)
   self.assertTrue(self.file.exists());self.assertEqual(len(self.library.list()),1)
 def test_loaded_nondefault_reference_is_protected(self):
  with self.assertRaisesRegex(ValueError,'Unload'):self.library.remove_reference(self.mid,loaded_path=str(self.file))
 def test_unrelated_transaction_is_neither_committed_nor_rolled_back(self):
  for action in ['remove','import']:
   self.con.execute('INSERT INTO chats VALUES(?,?)',('pending',''))
   with self.subTest(action=action),self.assertRaisesRegex(RuntimeError,'transaction'):
    if action=='remove':self.library.remove_reference(self.mid)
    else:self.library.import_file(str(self.file))
   self.assertTrue(self.con.in_transaction);self.assertEqual(self.con.execute('SELECT count(*) FROM chats').fetchone()[0],1)
   self.con.rollback();self.assertEqual(len(self.library.list()),1)
 def test_precancelled_load_and_unload_never_dispatch(self):
  cancel=threading.Event();cancel.set();engine=Mock()
  for op in ['load','unload']:
   with self.subTest(operation=op),self.assertRaisesRegex(RuntimeError,'cancelled'):self.library.action({'operation':op},engine,cancel,lambda _:None)
  engine.text_runtime.load.assert_not_called();engine.text_runtime.unload.assert_not_called()
 def test_late_cancel_keeps_truthful_unload_acknowledgement(self):
  engine=SimpleNamespace(resource_lock=threading.RLock(),text_runtime=Mock())
  worker=app.WorkspaceTask('controlled-unload','modelLibrary',{'operation':'unload'},self.ws,engine)
  engine.text_runtime.unload.side_effect=worker.cancel_event.set;results=[]
  worker.done.connect(lambda raw:results.append(json.loads(raw)));worker.run()
  self.assertTrue(results[0]['ok']);self.assertTrue(results[0]['value']['unloaded']);self.assertTrue(results[0]['value']['cancelAfterCommit'])

class RuntimeIdentity(unittest.TestCase):
 def test_running_conversation_model_is_not_mislabeled_as_default_or_unloadable(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);default=root/'default.gguf';loaded=root/'conversation.gguf';default.write_bytes(b'not a model');loaded.write_bytes(b'not a model')
   manager=EngineManager();manager.cfg={'chat_backend':'bundled','gpt_oss_gguf':str(default),'chat_context':4096}
   manager.runtime=SimpleNamespace(ready=True,_is_healthy=lambda:True,model_path=str(loaded),projector_path='',model_descriptor=None,process=SimpleNamespace(pid=123),context=2048)
   manager.chat_load_state='ready'
   manager.lm_runtime=SimpleNamespace(_lms_path=lambda:root/'missing',_bionic_path=lambda:root/'missing')
   manager.vision_model_status=lambda:{}
   memory={'available':4*1024**3,'total':16*1024**3,'pagefile_available':8*1024**3}
   with patch('integrated_runtime.physical_memory_status',return_value=memory),patch('integrated_runtime.available_cuda_memory',return_value=None):
    status=manager.chat_status();self.assertFalse(status['loaded']);self.assertTrue(status['runtimeLoaded']);self.assertEqual(status['runtimeModelPath'],str(loaded));self.assertEqual(status['runtimeModelName'],loaded.name)
    manager.chat_load_state='error';status=manager.chat_status();self.assertTrue(status['runtimeLoaded']);self.assertFalse(status['loaded'])

if __name__=='__main__':unittest.main()
