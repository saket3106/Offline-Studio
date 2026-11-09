"""Filesystem-only migration regressions; no engine/model/microphone loading."""
import ast, tempfile, types, unittest
from pathlib import Path
S=Path(__file__).resolve().parents[1]

def function(name,path,classname=None):
 tree=ast.parse(path.read_text(encoding='utf-8'))
 body=next(n.body for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname) if classname else tree.body
 n=next(n for n in body if isinstance(n,ast.FunctionDef) and n.name==name)
 n.decorator_list=[]
 return ast.Module(body=[n],type_ignores=[])

class RelocatedResources(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.source=self.root/'Source';self.source.mkdir()
  self.env={'Path':Path,'APP_DIR':self.source}
  exec(compile(function('resolve_path',S/'integrated_runtime.py'),'<source-path-function>','exec'),self.env)
  self.resolve=self.env['resolve_path']
 def tearDown(self):self.tmp.cleanup()
 def file(self,relative):
  p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture');return p.resolve()
 def test_existing_source_resource_wins(self):
  p=self.file('Source/same.gguf');self.file('Models/Chat/same.gguf');self.assertEqual(self.resolve('same.gguf'),p)
 def test_new_application_native_resource(self):
  p=self.file('Application/stable-diffusion/sd-cli.exe');self.assertEqual(self.resolve('stable-diffusion/sd-cli.exe'),p)
 def test_legacy_application_layout(self):
  p=self.file('Offline GPT/old.gguf');self.assertEqual(self.resolve('old.gguf'),p)
 def test_chat_model(self):
  p=self.file('Models/Chat/test.gguf');self.assertEqual(self.resolve('test.gguf'),p)
 def test_vision_projector(self):
  p=self.file('Models/Vision/projector.gguf');self.assertEqual(self.resolve('projector.gguf'),p)
 def test_image_vae(self):
  p=self.file('Models/Image/vae.safetensors');self.assertEqual(self.resolve('vae.safetensors'),p)
 def test_whisper_model_and_worker(self):
  p=self.file('Models/Whisper/ggml-large-v3-turbo-q5_0.bin')
  self.env['resolve_path']=self.resolve
  exec(compile(function('_path',S/'app.py','WhisperTranscriptionWorker'),'<source-worker-path>','exec'),self.env)
  self.assertEqual(self.env['_path'](types.SimpleNamespace(cfg={'voice_model_path':'whisper/models/'+p.name}),'voice_model_path'),p)
 def test_whisper_server(self):
  p=self.file('Application/whisper/whisper-server.exe');self.assertEqual(self.resolve('whisper-server.exe'),p)
 def test_kokoro_directory(self):
  p=self.file('Application/kokoro/model_quantized.onnx');self.assertEqual(self.resolve('kokoro'),p.parent)
 def test_explicit_subdirectory_is_not_discarded(self):
  self.file('Models/Chat/test.gguf');self.assertEqual(self.resolve('unselected/test.gguf'),(self.source/'unselected/test.gguf').resolve())
 def test_missing_model_does_not_select_another(self):
  self.file('Models/Chat/other.gguf');self.assertFalse(self.resolve('missing.gguf').exists())
 def test_models_directory_cannot_supply_program(self):
  self.file('Models/Chat/helper.exe');self.assertFalse(self.resolve('helper.exe').exists())
 def test_absolute_selection_preserved(self):
  p=self.file('Chosen/test.gguf');self.assertEqual(self.resolve(str(p)),p)

if __name__=='__main__':unittest.main()
