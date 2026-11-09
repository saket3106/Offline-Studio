"""Focused Nov 4 regressions: real loopback transport and request/state identity."""
import json
import threading
import time
import unittest
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from integrated_runtime import EngineManager
from live_voice import LiveVoiceSession
from voice_transport import transcribe_request


class VoiceTransportTests(unittest.TestCase):
    def setUp(self):
        self.requests=[]
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                owner.requests.append(self.path)
                self.rfile.read(int(self.headers['Content-Length']))
                if owner.mode=='disconnect':
                    self.connection.close();return
                if owner.mode=='delay':time.sleep(.4)
                self.send_response(503 if owner.mode=='error' else 200)
                self.end_headers()
                try:self.wfile.write(b'{"text":"actual fixture response"}')
                except OSError:pass
        self.mode='ok';self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.addCleanup(self.server.server_close);self.addCleanup(self.server.shutdown)
    def request(self,event=None,timeout=2):
        return transcribe_request(self.server.server_port,b'fixture','application/octet-stream',event or threading.Event(),timeout)
    def test_one_successful_post(self):
        self.assertEqual(json.loads(self.request())['text'],'actual fixture response');self.assertEqual(self.requests,['/inference'])
    def test_ambiguous_disconnect_is_not_replayed(self):
        self.mode='disconnect'
        with self.assertRaises(Exception):self.request()
        self.assertEqual(len(self.requests),1)
    def test_http_error_is_not_replayed(self):
        self.mode='error'
        with self.assertRaisesRegex(RuntimeError,'503'):self.request()
        self.assertEqual(len(self.requests),1)
    def test_cancel_interrupts_delayed_headers(self):
        self.mode='delay';cancel=threading.Event();timer=threading.Timer(.04,cancel.set);timer.start()
        start=time.monotonic()
        with self.assertRaises(InterruptedError):self.request(cancel)
        self.assertLess(time.monotonic()-start,.25);self.assertEqual(len(self.requests),1)
    def test_deadline_interrupts_delayed_headers(self):
        self.mode='delay';start=time.monotonic()
        with self.assertRaises(TimeoutError):self.request(timeout=.05)
        self.assertLess(time.monotonic()-start,.3);self.assertEqual(len(self.requests),1)


class RequestIdentityTests(unittest.TestCase):
    def manager(self):
        manager=EngineManager.__new__(EngineManager);manager.cfg={'chat_backend':'bundled'}
        manager.chat_status=lambda:{'backend':'bundled','modelName':'Qwen 4B','modelPath':r'C:\models\four.gguf','loaded':False,'runtimeLoaded':True,'runtimeModelName':'Old 9B','runtimeModelPath':r'C:\models\nine.gguf','loadState':'not-loaded'}
        manager.resolve_model_path=lambda target:Path(target)
        return manager
    def test_next_request_does_not_claim_previous_loaded_model(self):
        value=self.manager().chat_identity_context(r'C:\models\four.gguf')
        self.assertEqual(value['displayName'],'Qwen 4B');self.assertFalse(value['loaded']);self.assertEqual(value['loadState'],'not-loaded')
    def test_conversation_override_is_independent_of_default(self):
        value=self.manager().chat_identity_context(r'C:\models\conversation.gguf')
        self.assertEqual(value['displayName'],'conversation.gguf');self.assertFalse(value['loaded'])
    def test_matching_runtime_is_loaded(self):
        value=self.manager().chat_identity_context(r'C:\models\nine.gguf')
        self.assertEqual(value['displayName'],'Old 9B');self.assertTrue(value['loaded'])
    def test_display_alias_uses_the_same_selection_resolver_as_inference(self):
        manager=self.manager();manager.resolve_model_path=lambda target:Path(r'C:\models\four.gguf') if target=='Qwen 4B' else Path(target)
        value=manager.chat_identity_context('Qwen 4B')
        self.assertEqual(value['displayName'],'Qwen 4B');self.assertTrue(value['modelPath'].endswith('four.gguf'));self.assertFalse(value['loaded'])


class VoiceCaptureReadinessTests(unittest.TestCase):
    def test_permission_without_pcm_has_bounded_failure(self):
        now=[0.];session=LiveVoiceSession(lambda e:None,lambda:now[0]);session.start('chat');session.tick(chat='chat',busy=False)
        session.begin_capture(session.session_id,session.generation,'chat',False,False)
        self.assertFalse(session.snapshot()['captureReady']);now[0]=16
        session.tick(chat='chat',busy=False);self.assertEqual(session.state,'error');self.assertIn('no audio',session.error)
    def test_actual_pcm_confirmation_keeps_capture_alive(self):
        now=[0.];session=LiveVoiceSession(lambda e:None,lambda:now[0]);session.start('chat');session.tick(chat='chat',busy=False)
        session.begin_capture(session.session_id,session.generation,'chat',False,False);session.capture_ready=True;now[0]=16
        session.tick(chat='chat',busy=False);self.assertEqual(session.state,'listening')


if __name__=='__main__':unittest.main()
