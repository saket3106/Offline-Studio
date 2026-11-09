"""Model/projector identity and multimodal evidence regressions; no native loads."""
from contextlib import nullcontext
from pathlib import Path
import tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from integrated_runtime import EngineManager,_LocalLlamaServer
from agent_resources import AgentSpecialists,AttachmentRegistry
from agent_workspace import WorkspaceAccess
from PIL import Image
if __package__:
    from .test_model_inspection import fixture
else:
    from test_model_inspection import fixture

class VisionPairStatusTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
  self.model=self.root/'model.gguf';self.projector=self.root/'projector.gguf';(self.root/'llama-server.exe').write_bytes(b'not executed')
  self.model.write_bytes(fixture([('general.architecture',8,'qwen3vl'),('general.name',8,'Qwen3-VL 8B')]))
  self.projector.write_bytes(fixture([('general.architecture',8,'clip'),('general.name',8,'Qwen3.5 projector')]))
  self.manager=EngineManager.__new__(EngineManager);self.manager.cfg={'vision_model':str(self.model),'vision_projector':str(self.projector)}
  for name in ['vision_test_state','vision_test_message','vision_test_answer','vision_test_time']:setattr(self.manager,name,'not-tested')
  patcher=patch('integrated_runtime.APP_DIR',self.root);patcher.start();self.addCleanup(patcher.stop)
 def test_known_projector_conflict_is_not_advertised_available(self):
  status=self.manager.vision_model_status();self.assertFalse(status['visionAvailable']);self.assertEqual(status['visionState'],'incompatible-projector')
  with self.assertRaisesRegex(RuntimeError,'Qwen3.5 projector'):self.manager._resolve_vision_model()
 def test_pair_observation_invalidates_cached_metadata_after_replacement(self):
  self.assertFalse(self.manager.vision_model_status()['visionAvailable'])
  self.projector.write_bytes(fixture([('general.architecture',8,'clip'),('general.name',8,'Qwen3-VL matching projector')]))
  status=self.manager.vision_model_status();self.assertTrue(status['visionAvailable']);self.assertEqual(status['visionArchitecture'],'qwen3vl');self.assertFalse(status['visionNativeVerified'])
 def test_repeated_status_reuses_header_review_without_reinspecting_weights(self):
  from model_inspection import inspect_gguf
  with patch('model_inspection.inspect_gguf',wraps=inspect_gguf) as inspect:
   for _ in range(20):self.manager.vision_model_status()
  self.assertEqual(inspect.call_count,2)
 def test_unchanged_invalid_header_is_not_reparsed_by_status_polling(self):
  from model_inspection import inspect_gguf
  self.projector.write_bytes(b'not GGUF')
  with patch('model_inspection.inspect_gguf',wraps=inspect_gguf) as inspect:
   for _ in range(20):self.assertFalse(self.manager.vision_model_status()['visionAvailable'])
  self.assertEqual(inspect.call_count,2)
 def test_status_consumer_cannot_mutate_cached_header_identity(self):
  status=self.manager.vision_model_status();expected=status['visionPairIdentity']['modelHeaderSha256']
  status['visionPairIdentity']['modelHeaderSha256']='not-an-observed-hash'
  self.assertEqual(self.manager.vision_model_status()['visionPairIdentity']['modelHeaderSha256'],expected)
 def test_invalid_gguf_fails_before_loading(self):
  self.projector.write_bytes(b'not GGUF')
  with patch('integrated_runtime.subprocess.Popen') as run:
   status=self.manager.vision_model_status();self.assertFalse(status['visionAvailable']);self.assertEqual(status['visionState'],'invalid-configuration')
   with self.assertRaises(RuntimeError):self.manager._resolve_vision_model()
  run.assert_not_called()

class RuntimeReuseTests(unittest.TestCase):
 def test_projector_replacement_invalidates_healthy_warm_server(self):
  with tempfile.TemporaryDirectory() as folder:
   model=Path(folder)/'model.gguf';projector=Path(folder)/'projector.gguf';model.write_bytes(b'model');projector.write_bytes(b'old projector')
   server=_LocalLlamaServer(folder);server.model_path=str(model.resolve());server.projector_path=str(projector.resolve());server.context=2048;server.loaded_gpu_layers='auto'
   server.model_file_observation=server.file_observation(model);server.projector_file_observation=server.file_observation(projector)
   projector.write_bytes(b'replaced incompatible projector')
   with patch.object(server,'_is_healthy',return_value=True),patch.object(server,'stop') as stop,patch.object(server,'_server_binary',side_effect=RuntimeError('restart required')):
    with self.assertRaisesRegex(RuntimeError,'restart required'):server.start(model,2048,'auto',lambda _:None,projector_path=projector)
   stop.assert_called_once()
 def test_unchanged_projector_reuses_healthy_server(self):
  with tempfile.TemporaryDirectory() as folder:
   model=Path(folder)/'model.gguf';projector=Path(folder)/'projector.gguf';model.write_bytes(b'model');projector.write_bytes(b'projector')
   server=_LocalLlamaServer(folder);server.model_path=str(model.resolve());server.projector_path=str(projector.resolve());server.context=2048;server.loaded_gpu_layers='auto'
   server.model_file_observation=server.file_observation(model);server.projector_file_observation=server.file_observation(projector)
   with patch.object(server,'_is_healthy',return_value=True),patch.object(server,'stop') as stop:
    server.start(model,2048,'auto',lambda _:None,projector_path=projector)
   stop.assert_not_called()

 def test_known_mismatch_is_rechecked_at_native_launch_boundary(self):
  from model_inspection import inspect_gguf
  from model_runtime import ModelInfo
  with tempfile.TemporaryDirectory() as folder:
   model=Path(folder)/'model.gguf';projector=Path(folder)/'projector.gguf'
   model.write_bytes(fixture([('general.architecture',8,'qwen3vl'),('general.name',8,'Qwen3-VL')]))
   projector.write_bytes(fixture([('general.architecture',8,'clip'),('general.name',8,'Qwen3.5 projector')]))
   server=_LocalLlamaServer(folder);server.model_descriptor=ModelInfo.from_inspection(inspect_gguf(model))
   with patch.object(server,'_server_binary',return_value=Path(folder)/'llama-server.exe'),patch.object(server,'_check_runtime_files'),patch.object(server,'inspect_behavior'),patch('integrated_runtime.subprocess.Popen') as run:
    with self.assertRaisesRegex(RuntimeError,'Qwen3.5 projector'):server.start(model,2048,'auto',lambda _:None,projector_path=projector)
   run.assert_not_called()

class CompletionIdentityTests(unittest.TestCase):
 def manager(self,diagnostics):
  m=EngineManager.__new__(EngineManager);m.cfg={'chat_backend':'bundled','gpt_oss_gguf':'default.gguf'};m.loaded_model='Actual conversation model'
  m.lock=threading.RLock();m._active_inference_count=0;m._current_generation_id=0;m.resource_lease=lambda _:nullcontext()
  m._cancel_idle_timer=Mock();m._schedule_idle_unload=Mock();m.check_emergency_memory=Mock();m.record_chat_test=Mock();m.ensure_chat=Mock()
  m.runtime=SimpleNamespace(model_descriptor=None,model_path='conversation.gguf',context=2048,ready=True,session_id='observed-session',last_generation_diagnostics=diagnostics)
  return m
 def test_truncated_and_broken_stream_never_record_complete_health_pass(self):
  for diagnostics in [{'finish_reason':'length'},{'finish_reason':'stop','stream_error':'connection lost'}]:
   with self.subTest(diagnostics=diagnostics):
    m=self.manager(diagnostics)
    with patch('integrated_runtime.ExistingTextAdapter') as adapter:
     adapter.return_value.complete.return_value='Preserved partial text';self.assertEqual(m.chat_completion([]),'Preserved partial text')
    self.assertEqual(m.last_completion_identity['completionState'],'PARTIAL');self.assertFalse(m.last_completion_identity['responseComplete'])
    self.assertEqual(m.record_chat_test.call_args.args[0],'partial')
 def test_completed_response_retains_requested_and_actual_generator_identities(self):
  m=self.manager({'finish_reason':'stop','generated_token_count':12})
  with patch('integrated_runtime.ExistingTextAdapter') as adapter:
   adapter.return_value.complete.return_value='A complete answer';m.chat_completion([],model='conversation-selection')
  identity=m.last_completion_identity;self.assertEqual(identity['completionState'],'COMPLETED');self.assertTrue(identity['responseComplete'])
  self.assertEqual(identity['requestedModel'],'conversation-selection');self.assertEqual(identity['modelPath'],'conversation.gguf');self.assertEqual(identity['configurationDefaultModel'],'default.gguf')
  self.assertEqual(m.record_chat_test.call_args.args[0],'passed')

 def test_loopback_runtime_exposes_local_provenance_and_completion_integrity(self):
  diagnostics={'finish_reason':'stop','stream_terminated':True,'generated_token_count':9,
               'prompt_token_count':17,'reasoning_present':False}
  m=EngineManager.__new__(EngineManager);m.cfg={'chat_backend':'lmstudio','chat_model':'configured/local-model'}
  m.loaded_model='configured/local-model';m.lock=threading.RLock();m._active_inference_count=0;m._current_generation_id=0
  m.resource_lease=lambda _:nullcontext();m._cancel_idle_timer=Mock();m._schedule_idle_unload=Mock();m.check_emergency_memory=Mock();m.record_chat_test=Mock();m.ensure_chat=Mock()
  m.runtime=SimpleNamespace(last_generation_diagnostics={})
  m.lm_runtime=SimpleNamespace(loaded_model='actual/local-model',last_generation_diagnostics=diagnostics)
  with patch('integrated_runtime.ExistingTextAdapter') as adapter:
   adapter.return_value.complete.return_value='A local answer'
   self.assertEqual(m.chat_completion([],model='requested/local-model'),'A local answer')
  identity=m.last_completion_identity
  self.assertEqual(identity['backend'],'lmstudio');self.assertEqual(identity['modelName'],'actual/local-model')
  self.assertEqual(identity['outputSource'],'local_model');self.assertEqual(identity['requestedModel'],'requested/local-model')
  self.assertEqual(identity['completionState'],'COMPLETED');self.assertTrue(identity['responseComplete'])
  self.assertTrue(identity['streamTerminated']);self.assertEqual(identity['generatedTokens'],9)
  self.assertEqual(identity['promptTokens'],17);self.assertEqual(identity['nativeAcceptance'],'not_established')

 def test_loopback_stream_without_done_marker_is_partial(self):
  m=self.manager({'finish_reason':None,'stream_terminated':False,'generated_token_count':4})
  m.cfg={'chat_backend':'lmstudio','chat_model':'configured/local-model'}
  m.lm_runtime=SimpleNamespace(loaded_model='actual/local-model',last_generation_diagnostics={'finish_reason':None,'stream_terminated':False,'generated_token_count':4})
  with patch('integrated_runtime.ExistingTextAdapter') as adapter:
   adapter.return_value.complete.return_value='A truncated local answer'
   self.assertEqual(m.chat_completion([]),'A truncated local answer')
  self.assertEqual(m.last_completion_identity['completionState'],'PARTIAL')
  self.assertFalse(m.last_completion_identity['responseComplete'])

class VisualEvidenceIdentityTests(unittest.TestCase):
 def test_switching_vision_pair_does_not_relabel_cached_pixel_evidence(self):
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);Image.new('RGB',(8,8),'blue').save(root/'misleading-car.png');calls=[]
   status={'visionAvailable':True,'visionModel':'first model','visionModelKey':'first.gguf','visionProjectorPath':'first-mmproj.gguf'}
   def infer(requests,**kwargs):calls.append(status['visionModel']);return ['Blue pixels, no vehicle established.']
   engine=SimpleNamespace(vision_model_status=lambda:dict(status),vision_completions=infer);access=WorkspaceAccess(root)
   try:
    service=AgentSpecialists(engine,access,AttachmentRegistry());first=service.inspect_image('workspace:misleading-car.png','Describe pixels',threading.Event())
    status.update(visionModel='second model',visionModelKey='second.gguf',visionProjectorPath='second-mmproj.gguf')
    second=service.inspect_image('workspace:misleading-car.png','Describe pixels',threading.Event())
    self.assertEqual(len(calls),2);self.assertEqual(first['provider'],'first model');self.assertEqual(second['provider'],'second model')
    self.assertEqual(second['source'],'workspace:misleading-car.png');self.assertTrue(second['pixelInferencePerformed'])
   finally:access.close()

 def test_identical_pixels_use_one_inference_and_keep_distinct_source_ids(self):
  import json
  with tempfile.TemporaryDirectory() as folder:
   root=Path(folder);Image.new('RGB',(8,8),'blue').save(root/'first.png');(root/'second.png').write_bytes((root/'first.png').read_bytes());requests=[]
   def infer(batch,**kwargs):requests.extend(batch);return ['A blue square.']*len(batch)
   engine=SimpleNamespace(vision_model_status=lambda:{'visionAvailable':True,'visionModel':'configured-name'},vision_completions=infer,last_vision_identity={'modelName':'actual native generator','modelPath':'verified.gguf','completionState':'COMPLETED','nativeReady':True})
   access=WorkspaceAccess(root)
   try:
    service=AgentSpecialists(engine,access,AttachmentRegistry());results=service.inspect_images(['workspace:first.png','workspace:second.png'],'Describe pixels',threading.Event())
    self.assertEqual(len(requests),1);self.assertEqual([r['source'] for r in results],['workspace:first.png','workspace:second.png'])
    self.assertTrue(all(r['provider']=='actual native generator' for r in results));json.dumps(results)
   finally:access.close()

if __name__=='__main__':unittest.main()
