"""Independent presentation contract tests: real bridge bodies, no model or user store."""
import ast,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from ui_preferences import DEFAULTS,read,validate
S=Path(__file__).resolve().parents[1]
class PreferenceTests(unittest.TestCase):
 def test_all_supported_choices_and_boundaries(self):
  from ui_preferences import CHOICES,RANGES
  for key,choices in CHOICES.items():
   for choice in choices:self.assertEqual(validate({key:choice}),{key:choice})
  for key,(lo,hi) in RANGES.items():
   for value in [lo,hi]:self.assertEqual(validate({key:value})[key],value)
 def test_adversarial_types_and_out_of_range(self):
  cases=[None,[],{}, {'unknown':'value'},{'theme':'system'},{'ui_density':'spacious'},{'ui_code_wrap':1},{'ui_code_wrap':'true'},{'ui_content_width':True},{'ui_chat_font_size':15.0},{'ui_chat_font_size':float('nan')},{'ui_content_width':639},{'ui_content_width':1121},{'ui_chat_font_size':12},{'ui_chat_font_size':21},{'ui_accent':'url(file:///private)'}]
  for value in cases:
   with self.subTest(value=value),self.assertRaises(ValueError):validate(value)
 def test_corrupt_persisted_values_fall_back_individually(self):
  result=read({'ui_density':'compact','ui_content_width':99999,'theme':'light','ui_code_wrap':'yes'})
  self.assertEqual(result,{**DEFAULTS,'ui_density':'compact','theme':'light'})
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.file=Path(self.tmp.name)/'config.json';self.events=[]
  self.file.write_text(json.dumps({'chat_backend':'bundled','gpt_oss_gguf':'existing.gguf','privateValue':42}))
  self.load=lambda:json.loads(self.file.read_text())
  self.save=lambda v:self.file.write_text(json.dumps(v,allow_nan=False))
  tree=ast.parse((S/'app.py').read_text(encoding='utf-8'));klass=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DesktopBridge')
  methods=[n for n in klass.body if isinstance(n,ast.FunctionDef) and n.name in {'getAppearancePreferences','saveAppearancePreferences','resetAppearancePreferences'}]
  for n in methods:n.decorator_list=[]
  scope={'json':json,'load_config':self.load,'save_config':self.save};exec(compile(ast.Module(body=methods,type_ignores=[]),str(S/'app.py'),'exec'),scope)
  self.host=SimpleNamespace(event=SimpleNamespace(emit=self.events.append),backend=SimpleNamespace(engines=SimpleNamespace(reload=Mock(side_effect=AssertionError('Presentation must not reload inference')))))
  for n in methods:setattr(self.host,n.name,scope[n.name].__get__(self.host))
 def test_real_bridge_save_read_reset_and_reopen(self):
  r=json.loads(self.host.saveAppearancePreferences(json.dumps({'theme':'light','ui_chat_font_size':18,'ui_content_width':1000,'ui_density':'compact'})))
  self.assertTrue(r['ok']);self.assertEqual(json.loads(self.host.getAppearancePreferences())['preferences'],r['preferences'])
  # New read from disk, not a retained frontend object.
  self.assertEqual(read(json.loads(self.file.read_text()))['ui_chat_font_size'],18)
  reset=json.loads(self.host.resetAppearancePreferences());self.assertEqual(reset['preferences'],DEFAULTS)
  self.assertEqual(self.load()['privateValue'],42);self.assertEqual(self.load()['gpt_oss_gguf'],'existing.gguf');self.host.backend.engines.reload.assert_not_called()
  self.assertEqual(len(self.events),2);self.assertEqual(json.loads(self.events[0])['type'],'appearancePreferences')
 def test_rejected_requests_do_not_write_or_emit(self):
  before=self.file.read_bytes()
  for raw in ['{}','[]','null','{"ui_content_width":true}','{"ui_chat_font_size":NaN}','{"ui_sidebar":"evil"}', 'x'*4097,'{', '{"gpt_oss_gguf":"different.gguf"}']:
   self.assertFalse(json.loads(self.host.saveAppearancePreferences(raw))['ok']);self.assertEqual(before,self.file.read_bytes())
  self.assertEqual(self.events,[])
 def test_write_failure_has_no_success_event(self):
  self.save=lambda _:(_ for _ in ()).throw(OSError('Disk is full'))
  # Replace the actual compiled bridge's dependency, not its behavior.
  self.host.saveAppearancePreferences.__func__.__globals__['save_config']=self.save
  r=json.loads(self.host.saveAppearancePreferences('{"ui_density":"compact"}'));self.assertFalse(r['ok']);self.assertIn('Disk is full',r['error']);self.assertFalse(self.events)
if __name__=='__main__':unittest.main()
