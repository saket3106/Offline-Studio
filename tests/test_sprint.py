import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app
from document_tools import extract_document_cached
from rag_engine import prepare_document_context, search_document_exact
from intelligence import analyze_request, build_system_prompt

PDF = Path(r"C:\Users\mesak\Downloads\SELF_LEARNING_Alex_Doe_Final.pdf")

class SprintDocumentTests(unittest.TestCase):
    @unittest.skipUnless(PDF.is_file(), 'Actual user PDF unavailable')
    def test_real_physical_pages_and_outline(self):
        text, meta = extract_document_cached(PDF, None)
        self.assertEqual(meta['pages'], 29)
        self.assertEqual([h['page'] for h in meta['headings']], [1,12,15,16,19,21,28])
        self.assertEqual(len(meta['page_map']), 29)
        self.assertEqual(meta['filename'], PDF.name)
        _, repeated = extract_document_cached(PDF, None)
        self.assertTrue(repeated['parse_cache_hit'])

    @unittest.skipUnless(PDF.is_file(), 'Actual user PDF unavailable')
    def test_actual_literal_workers_never_infer_or_edit(self):
        for phrase, page in [('Sample values for illustration only.',8),
              ('Replace the percentages with actual Google Forms results if survey responses are collected.',29),
              ('Purple satellites manufacture invisible bicycles 7391',None)]:
            worker=app.DocumentWorker('test','Search the attached PDF for the exact phrase "'+phrase+'".',str(PDF),'',None)
            answers,errors,metrics=[],[],[]
            worker.done.connect(answers.append);worker.failed.connect(errors.append);worker.metrics.connect(metrics.append)
            worker.run()
            self.assertEqual(errors,[])
            result=json.loads(answers[0])
            self.assertEqual(result['kind'],'answer')
            match=result['meta']['document_search']['matches'][0]
            self.assertEqual(match['pages'],[page] if page else [])
            self.assertEqual(match['found'],bool(page))
            self.assertEqual(metrics[-1]['model_calls'],0)
            self.assertEqual(metrics[-1]['prompt_tokens'],0)

    @unittest.skipUnless(PDF.is_file(), 'Actual user PDF unavailable')
    def test_bounded_grounded_evidence_and_index_reuse(self):
        text,meta=extract_document_cached(PDF,None)
        query='Are the performance comparison and questionnaire results actual measurements or illustrative examples?'
        telemetry={};context=prepare_document_context(text,query,PDF.name,3800,meta,telemetry)
        self.assertLessEqual(len(context),3800)
        self.assertIn('PDF page 8 |',context);self.assertIn('PDF page 29 |',context)
        self.assertIn('Sample values for illustration only.',context)
        self.assertIn('illustrative questionnaire-analysis',context)
        prepare_document_context(text,query,PDF.name,3800,meta,telemetry)
        self.assertTrue(telemetry['index_cache_hit'])
        analysis=analyze_request(query,True,context)
        system=build_system_prompt('policy',analysis,rag_context=context)
        self.assertLess(len(system),4600)
        self.assertNotIn('You MUST output',system)
        many=prepare_document_context(text,[query]*8,PDF.name,3800,meta)
        self.assertLessEqual(len(many),3800)

    def test_line_wrap_match_has_physical_page_and_matching_mode(self):
        text='An earlier page.\n\nWrap this\n   sentence.'
        meta={'page_map':[{'page':1,'start':0,'end':16},{'page':2,'start':18,'end':len(text)}]}
        result=search_document_exact(text,'Find exact phrase "Wrap this sentence."','test',meta)
        self.assertEqual(result['matches'][0]['pages'],[2])
        self.assertEqual(result['matches'][0]['locations'][0]['match_type'],'normalized_whitespace_case')


class SprintManagementTests(unittest.TestCase):
    def test_transactional_trash_restore_and_export_order(self):
        from document_tools import export_conversations
        import zipfile
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'DB_PATH',Path(folder)/'history.db'):
            store=app.Store();a=store.new_chat('First');b=store.new_chat('Second');other=store.new_chat('Preserved')
            file=Path(folder)/'original.txt';file.write_text('untouched')
            store.add(a,'user','Question',str(file));store.add(a,'assistant','Answer',metrics={'duration_seconds':2})
            store.add(b,'user','Second question')
            self.assertEqual(store.trash_chats([a,b,a,'unknown']),2)
            self.assertEqual([r[0] for r in store.chats()],[other])
            self.assertEqual(len(store.messages(a)),2)
            self.assertEqual(store.trash_chats([a,b],True),2)
            records=store.export_records([a,b])
            self.assertEqual([m['role'] for m in records[0]['messages']],['user','assistant'])
            for extension in ['md','txt','json','pdf','zip']:
                output=Path(folder)/('export.'+extension);export_conversations(records,output,True)
                self.assertGreater(output.stat().st_size,30)
            with zipfile.ZipFile(Path(folder)/'export.zip') as archive:
                self.assertEqual(archive.read('attachments/001/001-original.txt'),b'untouched')
            self.assertEqual(file.read_text(),'untouched');store.con.close()

    def test_response_version_keeps_ids_and_metrics_without_duplicate_request(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(app,'DB_PATH',Path(folder)/'history.db'):
            store=app.Store();cid=store.new_chat();store.add(cid,'user','Original request','attachment.pdf')
            store.add(cid,'assistant','Original answer',metrics={'duration_seconds':3,'request_id':'first'})
            mid=store.con.execute("SELECT id FROM messages WHERE role='assistant'").fetchone()[0]
            store.replacement_response=(cid,mid)
            self.assertEqual(store.messages(cid)[-1][0],'user')
            store.add(cid,'assistant','New answer',metrics={'duration_seconds':4,'request_id':'second'})
            self.assertEqual(len(store.messages(cid)),2)
            saved=json.loads(store.messages(cid)[-1][3]);self.assertEqual(saved['response_versions'][0]['content'],'Original answer')
            self.assertEqual(saved['response_versions'][0]['metrics']['duration_seconds'],3)
            self.assertEqual(store.con.execute("SELECT id FROM messages WHERE role='assistant'").fetchone()[0],mid)
            store.con.close();store=app.Store();self.assertEqual(json.loads(store.messages(cid)[-1][3])['request_id'],'second');store.con.close()

    def test_retry_cache_only_runtime_successes_with_failed_siblings(self):
        result=app.retry_successful_sections('1. Keep this answer.\n2. I could not complete this task.',
             {'runtime':{'task_statuses':{'1':'SUCCESS','2':'EXPLICIT_FAILURE'},'tasks_failed':[2]}})
        self.assertEqual(result,{1:'Keep this answer.'})
        self.assertEqual(app.retry_successful_sections('1. Answer',{'runtime':{'task_statuses':{'1':'SUCCESS'}}}),{})

    def test_speech_text_excludes_markdown_and_runtime_fields(self):
        text=app.spoken_response_text('# Answer\n**Hello** [friend](https://example.com).\n```python\nprint(1)\n```\nMETHOD: TOOL')
        self.assertIn('Hello friend.',text);self.assertIn('code block omitted',text)
        self.assertNotIn('print(1)',text);self.assertNotIn('https:',text);self.assertNotIn('METHOD:',text)


class SprintRetryTests(unittest.TestCase):
    def test_latest_retry_replays_original_request_and_attachment_without_new_turn(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        for prompt, answer, rel_attachment in [
            ('Explain TCP.', 'TCP is a transport protocol.', ''),
            ('Write a Python function.', '```python\ndef square(x):\n    return x*x\n```', ''),
            ('Explain the attached PDF.', 'A grounded document answer.', 'original.pdf'),
            ('Explain the attached PDF.', 'Document error: interrupted', 'original.pdf'),
        ]:
            with self.subTest(prompt=prompt,answer=answer), tempfile.TemporaryDirectory() as folder, patch.object(app,'DB_PATH',Path(folder)/'history.db'):
                import gc
                attachment = str(Path(folder) / rel_attachment) if rel_attachment else ''
                store=app.Store();cid=store.new_chat()
                store.add(cid,'user',prompt,attachment)
                store.add(cid,'assistant',answer,metrics={'duration_seconds':3})
                mid=store.con.execute('SELECT MAX(id) FROM messages').fetchone()[0]
                backend=SimpleNamespace(busy=False,current=cid,store=store,send=Mock())
                app.DesktopBridge.retryLastMessage(SimpleNamespace(backend=backend))
                args,kwargs=backend.send.call_args
                self.assertEqual(args[0],prompt)
                self.assertEqual(json.loads(args[1]),[attachment] if attachment else [])
                self.assertEqual(kwargs['replay_response'],mid)
                self.assertEqual(len(store.messages(cid)),2)
                store.con.close()
                del backend, store
                gc.collect()

    def test_retry_executes_only_failed_model_subtask(self):
        from types import SimpleNamespace
        from intelligence import analyze_request, build_system_prompt
        calls=[]
        class Engine:
            runtime=SimpleNamespace(last_generation_diagnostics={})
            def ensure_chat(self,*args):return 'local'
            def chat_completion(self,messages,**kwargs):
                calls.append(messages)
                kwargs['on_token']('2. New recovered answer.')
                return '2. New recovered answer.'
        prompt='1. Explain TCP.\n2. Explain UDP.'
        analysis=analyze_request(prompt);analysis['retry_task_results']={1:'Original successful TCP explanation.'}
        worker=app.ChatWorker('local',[{'role':'system','content':build_system_prompt('',analysis)},{'role':'user','content':prompt}],Engine(),analysis)
        answers,errors=[],[];worker.done.connect(answers.append);worker.failed.connect(errors.append);worker.run()
        self.assertEqual(errors,[]);self.assertEqual(len(calls),1)
        self.assertIn('Original successful TCP explanation.',answers[0]);self.assertIn('New recovered answer.',answers[0])
        # Existing controller prunes the generation request to pending IDs.
        self.assertNotIn('1. Explain TCP.',calls[0][-1]['content'])


class SprintCancellationTests(unittest.TestCase):
    def test_cancel_never_blocks_gui_on_http_reader_close(self):
        import threading,time
        done=threading.Event();release=threading.Event()
        class Connection:
            sock=None
            def close(self):release.wait(2);done.set()
        worker=app.CancelableWorker();worker._set_connection(Connection())
        started=time.perf_counter();worker.cancel()
        self.assertLess(time.perf_counter()-started,.1);self.assertTrue(worker.cancel_event.is_set())
        release.set();self.assertTrue(done.wait(1))

    def test_chat_cancel_finalizes_after_runtime_unwinds(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        backend=SimpleNamespace(active_kind='chat',operation_bubble=None,current='test',store=Mock(),
            completed_metrics=lambda:{'duration_seconds':1},operation_event_id='cancel',
            emit_frontend=Mock(),ready=Mock(),push_messages=Mock(),set_busy=Mock())
        app.App.worker_cancelled(backend,'')
        backend.set_busy.assert_called_once_with(False,'Stopped')
