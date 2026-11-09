"""Focused tokenizer/index tests and an opt-in real local ONNX acceptance benchmark."""
import contextlib,json,math,sqlite3,struct,tempfile,threading,time,unittest
from pathlib import Path
from types import SimpleNamespace

from knowledge_engine import KnowledgeStore,LocalEmbedding
from workspace_services import LocalWorkspace,migrate_database

MODEL_ROOT=Path(__file__).resolve().parents[2]/'Models/Embedding/all-MiniLM-L6-v2'


class TokenizerTests(unittest.TestCase):
    def encoder(self):
        encoder=LocalEmbedding.__new__(LocalEmbedding);encoder.lowercase=True;encoder.strip_accents=True;encoder.max_length=8
        encoder.vocab={token:index for index,token in enumerate(['[PAD]','[UNK]','[CLS]','[SEP]','cafe','hello',',','world','play','##ing','中'])};return encoder
    def test_basic_tokenization_lowercase_accents_and_punctuation(self):
        e=self.encoder();self.assertEqual([2,4,6,5,3],e.tokenize('CAFÉ, Hello'))
    def test_wordpiece_cjk_and_unknown_are_deterministic(self):
        e=self.encoder();self.assertEqual([2,8,9,10,1,3],e.tokenize('playing中 missing'))
    def test_controls_removed_and_input_budget_preserves_separator(self):
        e=self.encoder();self.assertEqual([2,5,3],e.tokenize('hel\x00lo'));result=e.tokenize('hello '*30);self.assertEqual(8,len(result));self.assertEqual(3,result[-1])
    def test_cancelled_encoder_does_not_start_inference(self):
        e=self.encoder();e.cancel=threading.Event();e.cancel.set()
        with self.assertRaises(InterruptedError):e._check()


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.con=sqlite3.connect(self.root/'offline_gpt.sqlite3',check_same_thread=False);self.addCleanup(self.con.close);migrate_database(self.con,self.root);self.ws=LocalWorkspace(self.con,threading.RLock(),self.root);self.k=KnowledgeStore(self.ws)
    def source(self,name,text,project=''):
        p=self.root/name;p.write_text(text,encoding='utf-8');return self.k.index([str(p)],project)[0]['id']
    def test_batched_vectors_and_index_status_are_persistent(self):
        ident=self.source('record.txt','Orchid calibration interval seventeen days.');calls=[]
        class Encoder:
            fingerprint='deterministic fixture, not a model'
            def encode_batch(self,texts):calls.append(list(texts));return [[1.0]+[0.0]*31 for _ in texts]
        status=self.k.embed_document(ident,Encoder());self.assertEqual(1,len(calls));self.assertEqual(32,status['dimensions']);self.assertEqual(1,self.k.semantic_status()['vectorCount']);self.assertIsNotNone(KnowledgeStore(self.ws).documents()['documents'][0]['embedding'])
    def test_incomplete_batch_rejected_before_vector_write(self):
        ident=self.source('record.txt','Orchid calibration interval seventeen days.')
        e=SimpleNamespace(fingerprint='bad',encode_batch=lambda texts:[])
        with self.assertRaisesRegex(ValueError,'incomplete'):self.k.embed_document(ident,e)
        self.assertEqual(0,self.k.semantic_status()['vectorCount'])
    def test_project_isolation_and_changed_missing_exclusion_for_vectors(self):
        alpha=self.source('alpha.txt','A bicycle puncture can be patched.','alpha');beta=self.source('beta.txt','A bicycle puncture cannot be patched.','beta')
        class Encoder:
            fingerprint='fixture-vector'
            def encode(self,text):return [1.0]+[0.0]*31
        e=Encoder();self.k.embed_document(alpha,e);self.k.embed_document(beta,e)
        rows=self.k.search('repair cycle','alpha',embedding=e);self.assertTrue(rows);self.assertTrue(all(r['documentId']==alpha for r in rows));self.assertEqual('semantic',rows[0]['retrieval'])
        (self.root/'alpha.txt').write_text('Altered source text',encoding='utf-8');self.assertEqual([],self.k.search('repair cycle','alpha',embedding=e));(self.root/'alpha.txt').unlink();self.assertEqual([],self.k.search('repair cycle','alpha',embedding=e))
    def test_unrelated_low_similarity_is_not_ranked_as_semantic_match(self):
        ident=self.source('record.txt','Orchid calibration interval seventeen days.')
        class Encoder:
            fingerprint='fixture-vector'
            def encode(self,text):return ([1.,0.]+[0.]*30) if 'Orchid' in text else ([0.,1.]+[0.]*30)
        e=Encoder();self.k.embed_document(ident,e);self.assertEqual([],self.k.search('quarks quantum fields',embedding=e))
    def test_deleting_index_removes_vectors_preserving_original(self):
        ident=self.source('record.txt','Orchid calibration interval seventeen days.');e=SimpleNamespace(fingerprint='fixture',encode=lambda _:[1.]+[0.]*31);self.k.embed_document(ident,e);self.k.remove(ident);self.assertEqual(0,self.k.semantic_status()['vectorCount']);self.assertTrue((self.root/'record.txt').is_file())
    def test_memory_edit_updates_scope_expiry_and_enabled_state(self):
        row=self.k.memory('save',{'kind':'preference','title':'Units','content':'Prefer metric','provenance':{'executionVerified':True}})
        self.k.memory('save',{'id':row['id'],'kind':'project','projectId':'beta','title':'Edited units','content':'Use SI units','expires':time.time()+60,'enabled':False})
        self.assertEqual([],self.k.memory('list',{}));saved=self.k.memory('list',{'projectId':'beta'})[0];self.assertFalse(saved['enabled']);self.assertEqual('project',saved['kind']);self.assertFalse(json.loads(saved['provenance'])['executionVerified']);self.assertEqual([],self.k.relevant_memory('SI units','beta'))
        self.k.memory('save',{'id':row['id'],'kind':'project','projectId':'beta','content':'Use SI units','enabled':True});self.assertTrue(self.k.relevant_memory('SI units','beta'))
    def test_cached_retention_requires_same_project_and_unchanged_bytes(self):
        packet={'id':'origin-fixture','query':'orchid','state':'COMPLETED','created':time.time(),'projectId':'','sources':[{'id':'K0123456789abcdef','title':'Orchid source','url':'https://example.org/source','fetchStatus':'FETCHED','excerpt':'Orchid calibration occurs seventeen days apart.','contentFingerprint':'synthetic-web-fingerprint'}]}
        self.k.save_run(packet);self.k.retain_research(packet['id']);source=self.k.search('Orchid')[0];self.assertEqual(packet['id'],source['originRunId']);self.assertEqual('synthetic-web-fingerprint',source['originalContentFingerprint'])
        cached=dict(packet,id='cached-fixture',sources=[dict(source,fetchStatus='CACHED_LOCAL_RESEARCH')]);self.k.save_run(cached);self.assertEqual([source['documentId']],self.k.retain_research(cached['id'])['savedDocuments'])
        with self.assertRaises(PermissionError):self.k.retain_research(cached['id'],'beta')
        Path(source['path']).write_text('Changed research',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'bytes changed'):self.k.retain_research(cached['id'])


def native_benchmark(output):
    """Real model vectors, temporary files/SQLite only; never a production profile."""
    import psutil
    if psutil.virtual_memory().available<2*1024**3:raise RuntimeError('Native embedding admission requires 2 GiB available RAM.')
    process=psutil.Process();before=process.memory_info().rss;peak=[before];finished=threading.Event()
    def sample():
        while not finished.wait(.02):peak[0]=max(peak[0],process.memory_info().rss)
    watcher=threading.Thread(target=sample,daemon=True);watcher.start();started=time.perf_counter();encoder=None
    try:
        encoder=LocalEmbedding(MODEL_ROOT/'onnx/model_quint8_avx2.onnx',MODEL_ROOT/'vocab.txt');loaded_ms=(time.perf_counter()-started)*1000
        corpus={
            'vehicle':'The car needs gasoline to power its engine.',
            'memory':'Resting overnight improves memory consolidation and learning.',
            'payment':'The bank transaction was declined because the balance was insufficient.',
            'repair':'A punctured cycle wheel can be fixed with a patch after removing the inner tube.',
            'whale':'Blue whales are marine mammals that feed on krill.',
            'garden':'A tomato plant requires sunlight and well-drained soil.',
            'music':'The violin produces sound through bowed strings.',
            'recipe':'Bake bread with flour, water and yeast.',
        }
        queries=[('The automobile requires petrol.','vehicle'),('How does sleep help the brain retain information?','memory'),('An online payment failed to go through.','payment'),('repair bicycle tires','repair')]
        with tempfile.TemporaryDirectory() as folder,contextlib.ExitStack() as connections:
            root=Path(folder);path=root/'offline_gpt.sqlite3';con=connections.enter_context(contextlib.closing(sqlite3.connect(path,check_same_thread=False)));migrate_database(con,root);ws=LocalWorkspace(con,threading.RLock(),root);store=KnowledgeStore(ws)
            for name,text in corpus.items():
                source=root/(name+'.txt');source.write_text(text,encoding='utf-8');store.index([str(source)])
            beta=root/'private-beta.txt';beta.write_text('The automobile requires petrol but this project says the engine is electric.',encoding='utf-8');store.index([str(beta)],project='beta')
            t=time.perf_counter()
            for doc in store.documents()['documents']:store.embed_document(doc['id'],encoder)
            index_ms=(time.perf_counter()-t)*1000;results=[]
            for query,target in queries:
                t=time.perf_counter();lexical=store.search(query);lexical_ms=(time.perf_counter()-t)*1000;t=time.perf_counter();hybrid=store.search(query,embedding=encoder);hybrid_ms=(time.perf_counter()-t)*1000
                def hit(rows):return bool(rows and Path(rows[0]['path']).stem==target)
                results.append({'query':query,'expected':target,'lexicalTop1':Path(lexical[0]['path']).stem if lexical else None,'hybridTop1':Path(hybrid[0]['path']).stem if hybrid else None,'lexicalCorrect':hit(lexical),'hybridCorrect':hit(hybrid),'lexicalMs':round(lexical_ms,3),'hybridMs':round(hybrid_ms,3),'similarity':hybrid[0]['semanticSimilarity'] if hybrid else None})
                assert all(Path(r['path']).name!='private-beta.txt' for r in hybrid)
            unrelated=store.search('Quantum chromodynamics describes quark color confinement.',embedding=encoder)
            keyword_lexical=store.search('gasoline');keyword_hybrid=store.search('gasoline',embedding=encoder)
            assert Path(keyword_lexical[0]['path']).stem==Path(keyword_hybrid[0]['path']).stem=='vehicle'
            sample_vectors=encoder.encode_batch(['The automobile requires petrol.','The car needs gasoline to power its engine.','Blue whales feed on krill.']);norms=[math.sqrt(sum(v*v for v in row)) for row in sample_vectors];assert all(abs(n-1)<1e-5 for n in norms)
            single=encoder.encode('The automobile requires petrol.');assert sum(a*b for a,b in zip(single,sample_vectors[0]))>.98
            count=store.semantic_status()['vectorCount'];con.close();con=connections.enter_context(contextlib.closing(sqlite3.connect(path,check_same_thread=False)));store=KnowledgeStore(LocalWorkspace(con,threading.RLock(),root));restored=store.search(queries[0][0],embedding=encoder);assert Path(restored[0]['path']).stem=='vehicle' and store.semantic_status()['vectorCount']==count, [(r['title'],r['semanticSimilarity'],r['score']) for r in restored]
            changed=root/'vehicle.txt';changed.write_text('This source has been changed externally.',encoding='utf-8');assert not any(Path(r['path']).stem=='vehicle' for r in store.search(queries[0][0],embedding=encoder));changed.unlink();assert not any(Path(r['path']).stem=='vehicle' for r in store.search(queries[0][0],embedding=encoder));con.close()
            result={'status':'PASS','scope':'Native local CPU encoder and temporary SQLite; no Qwen inference','model':encoder.info(),'loadMs':round(loaded_ms,3),'indexMs':round(index_ms,3),'indexedDocuments':len(corpus)+1,'vectorsPersisted':count,'restartPersistence':True,'projectIsolation':True,'changedAndDeletedSourcesExcluded':True,'keywordControl':{'query':'gasoline','lexicalTop1':'vehicle','hybridTop1':'vehicle'},'batchSingleCosineAgreement':sum(a*b for a,b in zip(single,sample_vectors[0])),'batchNote':'Dynamic int8 activation quantization can cause small batch/single differences; deterministic preprocessing and retrieval relevance are measured separately.','norms':norms,'queries':results,'lexicalTop1Correct':sum(r['lexicalCorrect'] for r in results),'hybridTop1Correct':sum(r['hybridCorrect'] for r in results),'unrelatedRejected':not unrelated,'rssBeforeBytes':before,'rssPeakBytes':max(peak[0],process.memory_info().rss),'availableRamBytes':psutil.virtual_memory().available}
            assert result['hybridTop1Correct']==len(queries),result;assert result['unrelatedRejected'],unrelated
            output=Path(output);output.write_text(json.dumps(result,indent=2),encoding='utf-8');return result
    finally:
        finished.set();watcher.join(.1);LocalEmbedding.clear_cache()


if __name__=='__main__':
    import sys
    if len(sys.argv)==3 and sys.argv[1]=='--native-benchmark':print(json.dumps(native_benchmark(sys.argv[2]),indent=2))
    else:unittest.main()
