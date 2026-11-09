"""Additive knowledge/retention layer over the existing workspace document index."""
from pathlib import Path
import hashlib,json,math,re,struct,time,unicodedata,uuid


def tokens(text):return re.findall(r'\w+',unicodedata.normalize('NFKC',str(text)).casefold(),re.UNICODE)


class LocalEmbedding:
    """Bounded local BERT/WordPiece encoder with attention-mask pooling.

    One cached CPU session, never remote inference. Instances own cancellation;
    the cache owns only immutable tokenizer/model state and a serialized session.
    clear_cache() is available to the existing heavyweight model scheduler.
    """
    VERSION=2
    _cache={}
    _cache_lock=__import__('threading').RLock()
    _cache_seconds=90
    def __init__(self,model,vocab,cancel=None):
        import threading
        self.cancel=cancel;self.model=Path(model).absolute();self.vocab_path=Path(vocab).absolute()
        for path in (self.model,self.vocab_path):
            if not path.is_file():raise ValueError('Embedding artifact is missing: '+str(path))
            for part in (path,*path.parents):
                if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PermissionError('Redirected embedding artifacts are unavailable.')
        self.model_sha=self._digest(self.model);self.vocab_sha=self._digest(self.vocab_path)
        cfg_path=self.vocab_path.parent/'tokenizer_config.json';cfg=json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.is_file() else {}
        if cfg.get('tokenizer_class','BertTokenizer') not in {'BertTokenizer','BertTokenizerFast'}:raise ValueError('Only local BERT WordPiece tokenizers are supported by this encoder.')
        self.lowercase=bool(cfg.get('do_lower_case',True));self.strip_accents=cfg.get('strip_accents')
        if self.strip_accents is None:self.strip_accents=self.lowercase
        self.max_length=256
        length_path=self.vocab_path.parent/'sentence_bert_config.json'
        if length_path.is_file():self.max_length=max(8,min(512,int(json.loads(length_path.read_text()).get('max_seq_length',256))))
        identity={'modelSha256':self.model_sha,'vocabSha256':self.vocab_sha,'preprocessingVersion':self.VERSION,'lowercase':self.lowercase,'stripAccents':self.strip_accents,'maxLength':self.max_length,'pooling':'attention-mask-mean-l2'}
        self.fingerprint=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest();self._check();started=time.perf_counter()
        with self._cache_lock:
            now=time.monotonic()
            for key,entry in list(self._cache.items()):
                if key!=self.fingerprint or now-entry['used']>self._cache_seconds:self._cache.pop(key)
            entry=self._cache.get(self.fingerprint)
            if entry is None:
                import onnxruntime as ort
                values=self.vocab_path.read_text(encoding='utf-8').splitlines()
                if len(values)!=len(set(values)):raise ValueError('Embedding vocabulary contains duplicate tokens.')
                vocabulary={value:i for i,value in enumerate(values)}
                for name in ['[UNK]','[CLS]','[SEP]','[PAD]']:
                    if name not in vocabulary:raise ValueError('Embedding vocabulary is missing '+name)
                options=ort.SessionOptions();options.intra_op_num_threads=2;options.inter_op_num_threads=1
                options.enable_cpu_mem_arena=False
                session=ort.InferenceSession(str(self.model),sess_options=options,providers=['CPUExecutionProvider'])
                inputs=session.get_inputs()
                if not inputs or any(item.name not in {'input_ids','attention_mask','token_type_ids'} or item.type!='tensor(int64)' for item in inputs):raise ValueError('Unsupported embedding ONNX inputs; expected BERT int64 inputs.')
                entry={'session':session,'vocab':vocabulary,'lock':threading.RLock(),'used':now}
                self._cache[self.fingerprint]=entry
            self.session=entry['session'];self.vocab=entry['vocab'];self._run_lock=entry['lock'];entry['used']=now
        self.load_ms=round((time.perf_counter()-started)*1000,2);self.last_dimensions=None
    @staticmethod
    def _digest(path):
        with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
    @classmethod
    def clear_cache(cls):
        with cls._cache_lock:cls._cache.clear()
    @classmethod
    def cached(cls):
        with cls._cache_lock:return {'sessions':len(cls._cache),'expirySeconds':cls._cache_seconds}
    def _check(self):
        if self.cancel and self.cancel.is_set():raise InterruptedError('Embedding cancelled.')
    def tokenize(self,text):
        # The BERT BasicTokenizer rules: clean controls, split CJK/punctuation,
        # lowercase and optionally strip combining accents before WordPiece.
        cleaned=[]
        for char in str(text):
            number=ord(char);category=unicodedata.category(char)
            if char in '\t\n\r' or category=='Zs':cleaned.append(' ')
            elif number in (0,0xfffd) or category.startswith('C'):continue
            elif 0x4e00<=number<=0x9fff or 0x3400<=number<=0x4dbf or 0x20000<=number<=0x2fa1f:cleaned.extend((' ',char,' '))
            else:cleaned.append(char)
        words=[]
        for word in ''.join(cleaned).split():
            if self.lowercase:word=word.lower()
            if self.strip_accents:word=''.join(c for c in unicodedata.normalize('NFD',word) if unicodedata.category(c)!='Mn')
            current=''
            for char in word:
                number=ord(char)
                if unicodedata.category(char).startswith('P') or 33<=number<=47 or 58<=number<=64 or 91<=number<=96 or 123<=number<=126:
                    if current:words.append(current);current=''
                    words.append(char)
                else:current+=char
            if current:words.append(current)
        pieces=[]
        for word in words:
            if len(word)>100:pieces.append('[UNK]');continue
            offset=0;local=[]
            while offset<len(word):
                end=len(word);found=None
                while end>offset:
                    candidate=('##' if offset else '')+word[offset:end]
                    if candidate in self.vocab:found=candidate;break
                    end-=1
                if found is None:local=['[UNK]'];break
                local.append(found);offset=end
            pieces.extend(local)
            if len(pieces)>=self.max_length-2:break
        return [self.vocab['[CLS]']]+[self.vocab.get(p,self.vocab['[UNK]']) for p in pieces[:self.max_length-2]]+[self.vocab['[SEP]']]
    def encode_batch(self,texts,batch_size=8):
        import numpy as np
        import onnxruntime as ort
        import threading
        texts=list(texts)
        if len(texts)>10000:raise ValueError('Embedding batch exceeds the document chunk budget.')
        results=[];batch_size=max(1,min(16,int(batch_size)))
        shape=self.session.get_inputs()[0].shape
        if shape and isinstance(shape[0],int):batch_size=min(batch_size,shape[0])
        for offset in range(0,len(texts),batch_size):
            self._check();items=[self.tokenize(t) for t in texts[offset:offset+batch_size]];width=max(len(item) for item in items)
            if len(shape)>1 and isinstance(shape[1],int):width=shape[1]
            if width<2 or width>512:raise ValueError('Embedding sequence dimension is unsupported.')
            ids=np.full((len(items),width),self.vocab['[PAD]'],dtype=np.int64);mask=np.zeros_like(ids)
            for row,item in enumerate(items):
                item=item[:width];item[-1]=self.vocab['[SEP]'];ids[row,:len(item)]=item;mask[row,:len(item)]=1
            arrays={'input_ids':ids,'attention_mask':mask,'token_type_ids':np.zeros_like(ids)};inputs={item.name:arrays[item.name] for item in self.session.get_inputs()}
            options=ort.RunOptions();finished=threading.Event()
            def cancel_run():
                while not finished.wait(.025):
                    if self.cancel and self.cancel.is_set():options.terminate=True;return
            watcher=threading.Thread(target=cancel_run,daemon=True,name='embedding-cancellation') if self.cancel else None
            if watcher:watcher.start()
            try:
                with self._run_lock:
                    self._check();output=np.asarray(self.session.run(None,inputs,run_options=options)[0],dtype=np.float32)
            except Exception:
                self._check();raise
            finally:
                finished.set()
                if watcher:watcher.join(.1)
            self._check()
            if output.ndim==3:
                if output.shape[:2]!=mask.shape:raise ValueError('Embedding sequence output disagrees with attention mask.')
                expanded=mask[:,:,None].astype(np.float32);output=(output*expanded).sum(axis=1)/np.maximum(expanded.sum(axis=1),1e-9)
            if output.ndim!=2 or output.shape[0]!=len(items) or not 32<=output.shape[1]<=4096 or not np.isfinite(output).all():raise ValueError('Invalid embedding output shape or values.')
            norms=np.linalg.norm(output,axis=1,keepdims=True)
            if np.any(norms<=0):raise ValueError('Embedding model returned a zero vector.')
            output=output/norms;self.last_dimensions=int(output.shape[1]);results.extend(output.tolist())
        return results
    def encode(self,text):return self.encode_batch([text],1)[0]
    def info(self):
        return {'model':self.model.name,'modelPath':str(self.model),'modelSha256':self.model_sha,'vocabSha256':self.vocab_sha,'fingerprint':self.fingerprint,'indexVersion':self.VERSION,'dimensions':self.last_dimensions,'provider':'CPUExecutionProvider','threads':2,'maxTokens':self.max_length,'pooling':'attention-mask mean + L2','loadMs':self.load_ms,'languages':'English semantic encoder when using all-MiniLM-L6-v2; Unicode lexical retrieval remains available for other languages.'}


class KnowledgeStore:
    def __init__(self,workspace):
        self.ws=workspace;self.con=workspace.con;self.lock=workspace.lock;self.directory=Path(workspace.directory)
        with self.lock:
            new_index=not self.con.execute("SELECT 1 FROM sqlite_master WHERE name='studio_chunks_fts'").fetchone()
            if new_index and self.con.execute("SELECT 1 FROM sqlite_master WHERE name='messages'").fetchone():
                if self.con.in_transaction:raise RuntimeError('Finish the current database transaction before initializing Knowledge.')
                from workspace_services import online_backup
                online_backup(self.con,self.directory/'backups','pre-knowledge')
        with self.lock,self.con:
            self.con.execute('CREATE TABLE IF NOT EXISTS studio_knowledge(document_id TEXT PRIMARY KEY,project_id TEXT NOT NULL DEFAULT "",kind TEXT,title TEXT,url TEXT,license TEXT,expires REAL,metadata TEXT)')
            self.con.execute('CREATE TABLE IF NOT EXISTS studio_vectors(chunk_id TEXT PRIMARY KEY,model_hash TEXT,dimensions INTEGER,vector BLOB)')
            self.con.execute('CREATE TABLE IF NOT EXISTS studio_research(id TEXT PRIMARY KEY,chat_id TEXT,project_id TEXT,query TEXT,state TEXT,created REAL,packet TEXT,saved INTEGER DEFAULT 0)')
            self.con.execute('CREATE TABLE IF NOT EXISTS studio_memories(id TEXT PRIMARY KEY,kind TEXT,project_id TEXT,title TEXT,content TEXT,provenance TEXT,created REAL,updated REAL,expires REAL,version INTEGER DEFAULT 1)')
            self.con.execute('CREATE VIRTUAL TABLE IF NOT EXISTS studio_chunks_fts USING fts5(chunk_id UNINDEXED,document_id UNINDEXED,text,tokenize="unicode61 remove_diacritics 2")')
            for statement in [
                "CREATE TRIGGER IF NOT EXISTS studio_chunks_insert AFTER INSERT ON document_chunks BEGIN INSERT INTO studio_chunks_fts VALUES(new.id,new.document_id,new.text); END",
                "CREATE TRIGGER IF NOT EXISTS studio_chunks_delete AFTER DELETE ON document_chunks BEGIN DELETE FROM studio_chunks_fts WHERE chunk_id=old.id; DELETE FROM studio_vectors WHERE chunk_id=old.id; END",
                "CREATE TRIGGER IF NOT EXISTS studio_chunks_update AFTER UPDATE ON document_chunks BEGIN DELETE FROM studio_chunks_fts WHERE chunk_id=old.id; INSERT INTO studio_chunks_fts VALUES(new.id,new.document_id,new.text); DELETE FROM studio_vectors WHERE chunk_id=old.id; END"]:self.con.execute(statement)
            # Incremental adoption of the existing index, not a second chunking stack.
            if new_index:self.con.execute('INSERT INTO studio_chunks_fts SELECT id,document_id,text FROM document_chunks WHERE id NOT IN (SELECT chunk_id FROM studio_chunks_fts)')
    def documents(self,project=None):
        query='SELECT d.id,d.path,d.hash,d.size,d.mtime_ns,d.metadata,d.indexed,k.project_id,k.kind,k.title,k.url,k.expires,k.metadata FROM workspace_documents d LEFT JOIN studio_knowledge k ON k.document_id=d.id';args=[]
        if project is not None:query+=' WHERE coalesce(k.project_id,"")=?';args.append(project)
        with self.lock:rows=self.con.execute(query+' ORDER BY d.indexed DESC',args).fetchall();chunks=self.con.execute('SELECT count(*) FROM document_chunks').fetchone()[0];vectors=self.con.execute('SELECT count(*) FROM studio_vectors').fetchone()[0]
        items=[]
        for row in rows:
            path=Path(row[1]);state='missing'
            if path.is_file():
                stat=path.stat();state='indexed' if stat.st_size==row[3] and stat.st_mtime_ns==row[4] else 'changed'
            items.append({'id':row[0],'path':row[1],'contentHash':row[2],'bytes':row[3],'indexedAt':row[6],'projectId':row[7] or '', 'kind':row[8] or 'document','title':row[9] or path.name,'url':row[10] or '', 'expires':row[11],'state':state,'expired':bool(row[11] and row[11]<time.time()),'metadata':json.loads(row[5] or '{}'),'embedding':json.loads(row[12] or '{}').get('embedding')})
        return {'documents':items,'chunks':chunks,'embeddedChunks':vectors,'databaseBytes':sum(p.stat().st_size for p in self.directory.glob('offline_gpt.sqlite3*') if p.is_file()),'embeddingIndex':self.semantic_status(project)}
    def index(self,paths,project='',cancel=None,emit=lambda _:None,embedding=None):
        result=[]
        for path in paths[:50]:
            if cancel and cancel.is_set():raise InterruptedError('Indexing cancelled.')
            emit({'stage':'INDEXING','detail':Path(path).name})
            row=self.ws.index([path],cancel=cancel)[0];doc_id=row['id']
            with self.lock,self.con:self.con.execute('INSERT INTO studio_knowledge(document_id,project_id,kind,title,metadata) VALUES(?,?,?,?,?) ON CONFLICT(document_id) DO UPDATE SET project_id=excluded.project_id',(doc_id,project,'document',Path(path).name,'{}'))
            if embedding:self.embed_document(doc_id,embedding,cancel)
            result.append(row)
        return result
    def embed_document(self,doc_id,embedding,cancel=None):
        started=time.perf_counter()
        with self.lock:
            rows=self.con.execute('SELECT c.id,c.text FROM document_chunks c LEFT JOIN studio_vectors v ON v.chunk_id=c.id WHERE c.document_id=? AND (v.chunk_id IS NULL OR v.model_hash!=?)',(doc_id,embedding.fingerprint)).fetchall()
            document=self.con.execute('SELECT path FROM workspace_documents WHERE id=?',(doc_id,)).fetchone()
        if not document:raise ValueError('Embedding source no longer exists in the index.')
        if len(rows)>10000:raise ValueError('Embedding source exceeds the bounded 10000-chunk budget.')
        for offset in range(0,len(rows),8):
            if cancel and cancel.is_set():raise InterruptedError('Embedding cancelled.')
            batch=rows[offset:offset+8]
            vectors=embedding.encode_batch([text for _,text in batch]) if hasattr(embedding,'encode_batch') else [embedding.encode(text) for _,text in batch]
            if len(vectors)!=len(batch):raise ValueError('Embedding model returned an incomplete batch.')
            if cancel and cancel.is_set():raise InterruptedError('Embedding cancelled.')
            with self.lock,self.con:
                for (ident,_),vector in zip(batch,vectors):
                    if not vector or not all(math.isfinite(float(v)) for v in vector):raise ValueError('Embedding vector is empty or nonfinite.')
                    self.con.execute('INSERT OR REPLACE INTO studio_vectors VALUES(?,?,?,?)',(ident,embedding.fingerprint,len(vector),struct.pack('<'+'f'*len(vector),*vector)))
        with self.lock,self.con:
            self.con.execute('INSERT OR IGNORE INTO studio_knowledge(document_id,project_id,kind,title,metadata) VALUES(?,?,?,?,?)',(doc_id,'','document',Path(document[0]).name,'{}'))
            current=self.con.execute('SELECT metadata FROM studio_knowledge WHERE document_id=?',(doc_id,)).fetchone();metadata=json.loads(current[0] or '{}')
            count,dimensions=self.con.execute('SELECT count(*),max(v.dimensions) FROM studio_vectors v JOIN document_chunks c ON c.id=v.chunk_id WHERE c.document_id=? AND v.model_hash=?',(doc_id,embedding.fingerprint)).fetchone()
            metadata['embedding']={'fingerprint':embedding.fingerprint,'indexVersion':LocalEmbedding.VERSION,'dimensions':dimensions,'vectorCount':count,'lastIndexedAt':time.time(),'durationMs':round((time.perf_counter()-started)*1000,2)}
            if hasattr(embedding,'info'):metadata['embedding']['model']=embedding.info()
            self.con.execute('UPDATE studio_knowledge SET metadata=? WHERE document_id=?',(json.dumps(metadata,ensure_ascii=False),doc_id))
        return metadata['embedding']
    def semantic_status(self,project=None):
        sql='SELECT k.metadata FROM studio_knowledge k'
        with self.lock:
            rows=self.con.execute(sql+(' WHERE k.project_id=?' if project is not None else ''),(project,) if project is not None else ()).fetchall()
            counts=self.con.execute('SELECT v.model_hash,v.dimensions,count(*) FROM studio_vectors v JOIN document_chunks c ON c.id=v.chunk_id LEFT JOIN studio_knowledge k ON k.document_id=c.document_id'+(' WHERE coalesce(k.project_id,"")=?' if project is not None else '')+' GROUP BY v.model_hash,v.dimensions',(project,) if project is not None else ()).fetchall()
        records=[json.loads(row[0] or '{}').get('embedding') for row in rows];records=[r for r in records if r]
        return {'indexVersion':LocalEmbedding.VERSION,'models':[{'fingerprint':r[0],'dimensions':r[1],'vectors':r[2]} for r in counts],'vectorCount':sum(r[2] for r in counts),'lastSuccessfulIndexing':max((r.get('lastIndexedAt',0) for r in records),default=None),'lastIndexDurationMs':max(records,key=lambda r:r.get('lastIndexedAt',0)).get('durationMs') if records else None,'cachedSessions':LocalEmbedding.cached()['sessions']}
    def search(self,query,project='',limit=6,embedding=None):
        stopwords={'a','an','and','are','as','at','be','by','can','do','does','for','from','how','i','in','is','it','of','on','or','that','the','their','this','to','was','what','when','where','which','who','with'}
        terms=[term for term in dict.fromkeys(tokens(query)) if term not in stopwords][:24]
        if not terms:return []
        expression=' OR '.join('"'+t.replace('"','""')+'"' for t in terms)
        sql='SELECT c.id,c.document_id,c.page,c.section,c.start,c.end,c.text,d.path,d.hash,k.title,k.url,k.kind,k.metadata FROM studio_chunks_fts f JOIN document_chunks c ON c.id=f.chunk_id JOIN workspace_documents d ON d.id=c.document_id LEFT JOIN studio_knowledge k ON k.document_id=d.id WHERE studio_chunks_fts MATCH ? AND coalesce(k.project_id,"")=? AND (k.expires IS NULL OR k.expires>?) ORDER BY bm25(studio_chunks_fts) LIMIT 40'
        with self.lock:lexical=self.con.execute(sql,(expression,project,time.time())).fetchall()
        scores={row[0]:1/(61+i) for i,row in enumerate(lexical)};records={row[0]:row for row in lexical};lexical_ranks={row[0]:i+1 for i,row in enumerate(lexical)};semantic_scores={}
        if embedding:
            # Weak one-word lexical overlap must not outrank a strong paraphrase.
            # Preserve FTS order while weighting coverage, then fuse calibrated
            # semantic confidence rather than treating every ranked hit equally.
            for ident,row in records.items():scores[ident]*=max(.25,len(set(terms).intersection(tokens(row[6])))/len(terms))
            query_vector=embedding.encode(query)
            with self.lock:rows=self.con.execute('SELECT v.chunk_id,v.dimensions,v.vector FROM studio_vectors v JOIN document_chunks c ON c.id=v.chunk_id JOIN studio_knowledge k ON k.document_id=c.document_id WHERE v.model_hash=? AND k.project_id=? AND (k.expires IS NULL OR k.expires>?) LIMIT 10000',(embedding.fingerprint,project,time.time())).fetchall()
            ranking=[]
            for ident,dimensions,raw in rows:
                if dimensions==len(query_vector):ranking.append((sum(a*b for a,b in zip(query_vector,struct.unpack('<'+'f'*dimensions,raw))),ident))
            for rank,(score,ident) in enumerate(sorted(ranking,reverse=True)[:30]):
                if score<.35:continue
                semantic_scores[ident]=score
                scores[ident]=scores.get(ident,0)+2*score/(61+rank)
                if ident not in records:
                    with self.lock:records[ident]=self.con.execute('SELECT c.id,c.document_id,c.page,c.section,c.start,c.end,c.text,d.path,d.hash,k.title,k.url,k.kind,k.metadata FROM document_chunks c JOIN workspace_documents d ON d.id=c.document_id JOIN studio_knowledge k ON k.document_id=d.id WHERE c.id=?',(ident,)).fetchone()
        matches=[];seen=set()
        for ident in sorted(scores,key=lambda ident:(scores[ident],semantic_scores.get(ident,0)),reverse=True):
            row=records[ident];path=Path(row[7])
            if not path.is_file():continue
            with self.lock:stat_row=self.con.execute('SELECT size,mtime_ns FROM workspace_documents WHERE id=?',(row[1],)).fetchone()
            stat=path.stat()
            if (stat.st_size,stat.st_mtime_ns)!=tuple(stat_row):continue
            key=(row[1],row[2],row[4]//500)
            if key in seen:continue
            seen.add(key);citation='K'+hashlib.sha256((row[0]+row[8]).encode()).hexdigest()[:16]
            metadata=json.loads(row[12] or '{}');fetch_status='LOCAL_INDEX'
            if row[11]=='research' and metadata.get('originRunId') and metadata.get('fetchStatus')=='FETCHED':
                retained_root=self.directory/'knowledge'/'research'
                redirected=any(part.is_symlink() or getattr(part,'is_junction',lambda:False)() for part in [path,*path.parents])
                if redirected or not path.resolve().is_relative_to(retained_root.resolve()) or LocalEmbedding._digest(path)!=row[8]:continue
                fetch_status='CACHED_LOCAL_RESEARCH' 
            matches.append({'id':citation,'documentId':row[1],'chunkId':row[0],'title':row[9] or path.name,'url':row[10] or '', 'path':str(path),'page':row[2],'section':row[3],'start':row[4],'end':row[5],'excerpt':row[6][:1800],'contentFingerprint':row[8],'sourceType':row[11] or 'document','fetchStatus':fetch_status,'retrievedAt':time.time(),'score':scores[ident],'lexicalRank':lexical_ranks.get(ident),'semanticSimilarity':semantic_scores.get(ident),'originRunId':json.loads(row[12] or '{}').get('originRunId'),'originalContentFingerprint':json.loads(row[12] or '{}').get('contentFingerprint'),'sourceMetadata':json.loads(row[12] or '{}'),'retrieval':'hybrid' if ident in semantic_scores and ident in lexical_ranks else 'semantic' if ident in semantic_scores else 'lexical'})
            if len(matches)>=limit:break
        return matches
    def remove(self,doc_id):
        # Remove the index and metadata, never the original document.
        self.ws.remove(doc_id)
        with self.lock,self.con:self.con.execute('DELETE FROM studio_knowledge WHERE document_id=?',(doc_id,))
    def save_run(self,packet):
        audit={k:v for k,v in packet.items() if k!='pages'}
        with self.lock,self.con:
            self.con.execute('INSERT OR REPLACE INTO studio_research VALUES(?,?,?,?,?,?,?,coalesce((SELECT saved FROM studio_research WHERE id=?),0))',(packet['id'],packet.get('chatId',''),packet.get('projectId',''),packet['query'][:1000],packet['state'],packet['created'],json.dumps(audit,ensure_ascii=False),packet['id']))
            self.con.execute('DELETE FROM studio_research WHERE saved=0 AND id NOT IN (SELECT id FROM studio_research ORDER BY created DESC LIMIT 50)')
    def research(self):
        with self.lock:rows=self.con.execute('SELECT id,query,state,created,saved,project_id,packet FROM studio_research ORDER BY created DESC LIMIT 50').fetchall()
        return [{'id':r[0],'query':r[1],'state':r[2],'created':r[3],'saved':bool(r[4]),'projectId':r[5],'packet':json.loads(r[6])} for r in rows]
    def retain_research(self,run_id,project='',days=30):
        with self.lock:row=self.con.execute('SELECT packet FROM studio_research WHERE id=?',(run_id,)).fetchone()
        if not row:raise ValueError('Research record is unavailable.')
        packet=json.loads(row[0]);saved=[];folder=self.directory/'knowledge'/'research';folder.mkdir(parents=True,exist_ok=True)
        if packet.get('projectId','')!=project:raise PermissionError('Retain research in its original project; cross-project copying needs a separate explicit workflow.')
        for source in packet.get('sources',[]):
            if source.get('fetchStatus')=='CACHED_LOCAL_RESEARCH':
                with self.lock:existing=self.con.execute('SELECT d.path,d.hash,k.project_id,k.kind,k.metadata FROM workspace_documents d JOIN studio_knowledge k ON k.document_id=d.id WHERE d.id=?',(source.get('documentId',''),)).fetchone()
                if not existing or existing[2]!=project or existing[3]!='research':raise PermissionError('Cached research does not belong to this indexed project.')
                original=Path(existing[0]);historical=json.loads(existing[4] or '{}')
                if not original.is_file() or LocalEmbedding._digest(original)!=existing[1] or source.get('contentFingerprint')!=existing[1]:raise ValueError('Cached research bytes changed; reindex or refresh the source first.')
                if source.get('originRunId') and source['originRunId']!=historical.get('originRunId'):raise PermissionError('Cached research provenance differs from its retained origin.')
                with self.lock,self.con:self.con.execute('UPDATE studio_knowledge SET expires=? WHERE document_id=?',(time.time()+max(1,min(365,int(days)))*86400,source['documentId']))
                saved.append(source['documentId']);continue
            if source.get('fetchStatus')!='FETCHED':continue
            # Retain evidence that was actually read and presented; not an invented full-page archive.
            text=source.get('excerpt','')
            if not text:continue
            path=folder/(hashlib.sha256((source['url']+source['contentFingerprint']).encode()).hexdigest()+'.txt')
            if not path.exists():path.write_text(source['title']+'\n'+text,encoding='utf-8')
            doc=self.ws.index([str(path)])[0]['id'];metadata=dict(source,originRunId=packet['id'],retentionScope='verified fetched excerpt, not entire website')
            with self.lock,self.con:self.con.execute('INSERT OR REPLACE INTO studio_knowledge VALUES(?,?,?,?,?,?,?,?)',(doc,project,'research',source['title'],source['url'],source.get('license','Not established'),time.time()+max(1,min(365,int(days)))*86400,json.dumps(metadata)))
            saved.append(doc)
        with self.lock,self.con:self.con.execute('UPDATE studio_research SET saved=1 WHERE id=?',(run_id,))
        return {'savedDocuments':saved,'scope':'Fetched evidence excerpts; no model retraining.'}
    def memory(self,operation,args):
        if operation=='list':
            with self.lock:rows=self.con.execute('SELECT * FROM studio_memories WHERE project_id=? ORDER BY updated DESC LIMIT 200',(args.get('projectId',''),)).fetchall()
            return [dict(dict(zip(['id','kind','projectId','title','content','provenance','created','updated','expires','version'],row)),enabled=not json.loads(row[5] or '{}').get('disabled',False)) for row in rows]
        ident=args.get('id') or uuid.uuid4().hex
        if operation=='delete':
            with self.lock,self.con:self.con.execute('DELETE FROM studio_memories WHERE id=?',(ident,))
            return {'deleted':True}
        if args.get('kind') not in {'preference','project','research','procedure'}:raise ValueError('Choose a supported memory category.')
        content=str(args.get('content','')).strip()
        if not content or len(content)>8000:raise ValueError('Memory must contain 1–8000 characters.')
        with self.lock:previous=self.con.execute('SELECT provenance FROM studio_memories WHERE id=?',(ident,)).fetchone()
        provenance=args.get('provenance',{'authority':'explicit user-authored record','executionVerified':False})
        if not isinstance(provenance,dict):raise ValueError('Memory provenance must be an object.')
        provenance=dict(provenance)
        disabled=not bool(args['enabled']) if 'enabled' in args else bool(previous and json.loads(previous[0] or '{}').get('disabled'))
        provenance['disabled']=disabled;provenance=json.dumps(provenance,ensure_ascii=False)
        expires=args.get('expires')
        if expires is not None:
            expires=float(expires)
            if not math.isfinite(expires) or expires<0:raise ValueError('Memory expiry must be a finite timestamp.')
        with self.lock,self.con:self.con.execute('INSERT INTO studio_memories VALUES(?,?,?,?,?,?,?,?,?,1) ON CONFLICT(id) DO UPDATE SET kind=excluded.kind,project_id=excluded.project_id,title=excluded.title,content=excluded.content,provenance=excluded.provenance,expires=excluded.expires,updated=excluded.updated,version=studio_memories.version+1',(ident,args['kind'],args.get('projectId',''),str(args.get('title',''))[:200],content,provenance,time.time(),time.time(),expires))
        return {'id':ident,'saved':True,'executionAuthority':False}
    def relevant_memory(self,query,project=''):
        requested=set(tokens(query));rows=self.memory('list',{'projectId':project});found=[]
        for row in rows:
            if not row.get('enabled',True) or row['expires'] and row['expires']<time.time():continue
            score=len(requested.intersection(tokens(row['title']+' '+row['content'])))
            if score or row['kind']=='preference':found.append((score,row))
        return [row for _,row in sorted(found,key=lambda pair:pair[0],reverse=True)[:4]]
