import ast,json,subprocess,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
S=Path(__file__).resolve().parents[1]
NODE=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'
class EndpointTests(unittest.TestCase):
 def test_real_pcm_endpoint_noise_pauses_short_long_and_generation_fences(self):
  uri=(S/'frontend-source/src/voiceCapture.js').as_uri()
  js='''import assert from 'node:assert/strict';import {SpeechEndpoint,acceptsSession} from URI;
 const pcm=(x)=>new Int16Array(1600).fill(x*32767);let now=0;
 function feed(e,x,n){let r;for(let i=0;i<n;i++){now+=100;r=e.push(pcm(x),16000,now)}return r;}
 for(const amplitude of [0,.001,.003,.006]){const e=new SpeechEndpoint();assert(!feed(e,amplitude,100).finish);assert(!e.speech);}
 let e=new SpeechEndpoint();feed(e,.08,1);assert(!feed(e,0,20).finish);assert(!e.speech);
 e=new SpeechEndpoint();feed(e,.08,3);assert(!feed(e,0,6).finish);assert(feed(e,0,1).finish);
 e=new SpeechEndpoint();feed(e,.08,8);assert(!feed(e,0,6).finish);feed(e,.08,15);assert(!feed(e,0,6).finish);assert(feed(e,0,1).finish);
 e=new SpeechEndpoint();feed(e,.08,2);assert(feed(e,0,16).discard);
 e=new SpeechEndpoint();feed(e,.08,100);assert(!feed(e,0,6).finish);assert(feed(e,0,1).finish);
 const current={sessionId:'new',generation:20,revision:7};
 assert(!acceptsSession({sessionId:'old',generation:19,revision:100},current));
 assert(!acceptsSession({sessionId:'new',generation:20,revision:6},current));
 assert(acceptsSession({sessionId:'new',generation:20,revision:8},current));
 console.log('silence, noise, impulse, short speech, hesitation, long speech, weak burst and stale snapshots passed');
 '''.replace('URI',json.dumps(uri))
  r=subprocess.run([str(NODE),'--input-type=module','-e',js],capture_output=True,text=True,timeout=15)
  self.assertEqual(r.returncode,0,r.stderr)

 def test_drained_tts_stream_has_terminal_ack_without_another_media_event(self):
  import voice_runtime
  tree=ast.parse((S/'voice_runtime.py').read_text());node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='finish_stream')
  env={k:getattr(voice_runtime,k) for k in ('re','normalize_speech_text')};exec(compile(ast.Module([node],[]),'voice-runtime-method','exec'),env)
  fake=SimpleNamespace(token='turn',streaming=True,stream_buffer='',streaming_finished=False,chunks=['Already spoken.'],current=None,ready=[],inflight=False,next_index=1,text='Already spoken.',position=0,state='loading',_request_next=Mock(),stop=Mock(),idle=Mock(),emit=Mock())
  env['finish_stream'](fake)
  self.assertEqual(fake.state,'ready');self.assertFalse(fake.streaming);fake.emit.assert_called_once_with()
  fake.current={'index':0};fake.streaming=True;fake.state='speaking';fake.emit.reset_mock()
  env['finish_stream'](fake);self.assertEqual(fake.state,'speaking');fake.emit.assert_not_called()

 def test_warmup_error_without_synthesis_token_is_not_dropped(self):
  tree=ast.parse((S/'voice_runtime.py').read_text());node=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_read')
  env={'json':json};exec(compile(ast.Module([node],[]),'voice-runtime-method','exec'),env)
  process=SimpleNamespace(readAllStandardOutput=lambda:b'{"id":"warm","error":"model could not initialize"}\n')
  fake=SimpleNamespace(process=process,buffer=b'',token='',warmup_id='warm',state='warming',_fail=Mock(),emit=Mock())
  env['_read'](fake,process);fake._fail.assert_called_once_with('model could not initialize')

if __name__=='__main__':unittest.main()
