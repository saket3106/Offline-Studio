"""Workspace/Agent adapters to the single IntelligenceEngine; no separate model manager."""
from pathlib import Path
import hashlib,json,threading,time,uuid
from intelligence_engine import IntelligenceEngine,NetworkGrant
from knowledge_engine import LocalEmbedding,tokens


def regular_path(raw):
    path=Path(raw).absolute()
    for part in [path,*path.parents]:
        if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PermissionError('Linked or redirected knowledge sources are unavailable.')
    if not path.is_file():raise ValueError('Knowledge source is missing.')
    return path


def execute(workspace,config,args,cancel,emit=lambda _:None,engines=None):
    engine=IntelligenceEngine(workspace,config);knowledge=engine.knowledge;operation=args.get('operation','list');project=str(args.get('projectId',''))[:100]
    if operation=='health':return engine.health()
    if operation=='providerProbe':return engine.probe_provider(str(args.get('query') or 'Royal Enfield Hunter 350'),NetworkGrant(**args['_networkGrant']),cancel)
    if operation=='discoverImages':return engine.discover_images(str(args.get('query','')),NetworkGrant(**args['_networkGrant']),project,args.get('_chatId',''),cancel)
    if operation in {'savedReferences','removeReference','subjectComposite'}:
        from reference_workflow import ReferenceStore,composite_subject
        references=ReferenceStore(workspace)
        if operation=='savedReferences':return {'references':references.list(project)}
        if operation=='removeReference':return references.remove(args['referenceId'],project)
        reference=references.get(args['referenceId'],project)
        if not args.get('_trustedBackground'):raise PermissionError('Choose the background through the native picker.')
        value=composite_subject(reference['path'],args['_trustedBackground'],Path(workspace.directory)/'generated',rectangle=args.get('rectangle'),cancel=cancel)
        path=Path(value['path']);ident=uuid.uuid4().hex
        with workspace.lock,workspace.con:workspace.con.execute('INSERT INTO library_images(id,path,model,final_dimensions,created,file_size,deleted) VALUES(?,?,?,?,?,?,0)',(ident,str(path),'Subject-preserving composite',value['dimensions'],time.time(),path.stat().st_size))
        value['id']=ident;value['referenceId']=reference['id'];value['sourceUrl']=reference['sourceUrl'];return value
    if operation=='list':return knowledge.documents(project if args.get('filterProject') else None)
    if operation=='runs':return {'runs':[row for row in knowledge.research() if row.get('projectId','')==project]}
    if operation in {'index','reindex','embed'}:
        if operation=='index':paths=args.get('_trustedPaths',[])
        elif operation=='embed':
            records=knowledge.documents(project if args.get('filterProject') else None)['documents']
            if args.get('documentId'):
                records=[row for row in records if row['id']==args.get('documentId')]
            records=[row for row in records if row.get('state')=='indexed']
            if not records:raise ValueError('No unchanged indexed sources are available for semantic indexing.')
            if not engine.health()['embeddingAvailable']:raise ValueError('Configure a local ONNX encoder and vocabulary in Intelligence settings before building the semantic index.')
            from integrated_runtime import physical_memory_status
            if physical_memory_status().get('available',0)<2*1024**3:raise RuntimeError('Local embeddings require 2 GiB available RAM; lexical indexing remains available without an embedding model.')
            embedding=LocalEmbedding(engine.config['embedding_model_path'],engine.config['embedding_vocab_path'],cancel);results=[]
            for row in records:
                if cancel and cancel.is_set():raise InterruptedError('Semantic indexing cancelled.')
                emit({'stage':'EMBEDDING','detail':row['title']})
                results.append({'documentId':row['id'],'title':row['title'],'embedding':knowledge.embed_document(row['id'],embedding,cancel)})
            return {'embedded':len(results),'documents':results,'semantic':True}
        else:
            records=knowledge.documents()['documents'];row=next((r for r in records if r['id']==args.get('documentId')),None)
            if not row:raise ValueError('Indexed source is unavailable.')
            paths=[row['path']];project=row['projectId']
        if not paths:raise PermissionError('Choose knowledge sources through the native picker first.')
        paths=[str(regular_path(path)) for path in paths];embedding=None
        if engine.health()['embeddingAvailable']:
            from integrated_runtime import physical_memory_status
            if physical_memory_status().get('available',0)<2*1024**3:raise RuntimeError('Local embeddings require 2 GiB available RAM; lexical indexing remains available without an embedding model.')
            embedding=LocalEmbedding(engine.config['embedding_model_path'],engine.config['embedding_vocab_path'],cancel)
        return {'indexed':knowledge.index(paths,project,cancel,emit,embedding),'semantic':bool(embedding)}
    if operation=='remove':knowledge.remove(args['documentId']);return {'removed':True,'originalFilePreserved':True}
    if operation=='search':
        sources=engine.search(str(args.get('query','')),project,cancel)
        retrieval='hybrid FTS5 + local ONNX' if any(row.get('retrieval') in {'semantic','hybrid'} for row in sources) else 'local FTS5 lexical'
        return {'sources':sources,'retrieval':retrieval}
    if operation=='savedReferences':
        from reference_workflow import ReferenceStore
        return {'references':ReferenceStore(knowledge.ws).list(project)}
    if operation=='removeReference':
        from reference_workflow import ReferenceStore
        return ReferenceStore(knowledge.ws).remove(args['id'],project)
    if operation=='research':
        grant=NetworkGrant(**args['_networkGrant']) if args.get('_networkGrant') else None
        return engine.prepare(str(args.get('query','')),project=project,chat=args.get('_chatId',''),grant=grant,cancel=cancel,emit=emit)
    if operation=='retain':return knowledge.retain_research(args['runId'],project,engine.config['research_retention_days'])
    if operation=='references':return {'references':engine.reference_candidates(args['runId'])}
    if operation=='downloadReference':
        return engine.download_reference(args['runId'],int(args['index']),NetworkGrant(**args['_networkGrant']),cancel)
    if operation=='memories':return {'memories':knowledge.memory('list',args)}
    if operation=='saveMemory':
        prior=next((row for row in knowledge.memory('list',{'projectId':project}) if row['id']==args.get('id')),None)
        if args.get('id') and not prior:raise PermissionError('Memory is unavailable in this project.')
        unchanged=prior and all(args.get(key,prior[key])==prior[key] for key in ['content','title','kind'])
        provenance=json.loads(prior['provenance']) if unchanged else {'authority':'explicit user-authored memory','executionVerified':False}
        args=dict(args,provenance=provenance);return knowledge.memory('save',args)
    if operation=='deleteMemory':
        if not any(row['id']==args.get('id') for row in knowledge.memory('list',{'projectId':project})):raise PermissionError('Memory is unavailable in this project.')
        return knowledge.memory('delete',args)
    if operation=='reuseProcedure':
        record=next((row for row in knowledge.memory('list',{'projectId':project}) if row['id']==args.get('id') and row['kind']=='procedure' and row.get('enabled',True)),None)
        if not record or record.get('expires') and record['expires']<time.time():raise ValueError('This procedure is unavailable or expired.')
        provenance=json.loads(record['provenance']);body=json.loads(record['content'])
        if not provenance.get('executionVerified'):raise PermissionError('This is user-authored context, not an observed successful procedure.')
        return {'id':record['id'],'prompt':str(args.get('query') or body['trigger']),'steps':body['steps'],'sourceRunId':provenance['sourceRunId'],'requiresFreshPermissions':True,'executionAuthority':False,'reviewBeforeSend':True}
    if operation=='saveProcedure':
        run=next((row['packet'] for row in knowledge.research() if row['id']==args.get('runId')),None)
        if not run or run.get('projectId','')!=project or run['state']!='COMPLETED' or run.get('citationValidation',{}).get('status')!='PASS' or not run.get('counts',{}).get('fetched') or not run.get('counts',{}).get('cited'):raise ValueError('Only a completed, citation-validated workflow in this project can become a verified research procedure.')
        steps=[{'stage':event['stage'],'detail':event['detail']} for event in run.get('events',[]) if event['stage'] in {'SEARCHING','READING','ANALYZED'}]
        record={'kind':'procedure','title':args.get('title') or run['query'][:100],'content':json.dumps({'trigger':run['query'],'steps':steps,'permissions':['fresh network permission','explicit approval for writes'],'successCriteria':['sources fetched','citations validated'],'executionAuthority':False},ensure_ascii=False),'projectId':project,'provenance':{'sourceRunId':run['id'],'executionVerified':True,'verifiedScope':'observed bounded research sequence, not universal correctness','traceSha256':hashlib.sha256(json.dumps(steps,sort_keys=True).encode()).hexdigest()}}
        return knowledge.memory('save',record)
    raise ValueError('Unsupported intelligence operation.')


INTELLIGENCE_TOOLS={'research_web','search_knowledge','save_research'}


class AgentIntelligence:
    def __init__(self,workspace,config,prompt,grant,project='',chat='',emit=lambda _:None):
        self.engine=IntelligenceEngine(workspace,config);self.prompt=prompt;self.grant=grant;self.project=project;self.chat=chat;self.emit=emit;self.packet=None;self.completed_queries={};self.query_used=0;self.pages_used=0
    def available(self):return {'search_knowledge','save_research'}|({'research_web'} if self.grant and self.grant.allowed and self.engine.config['intelligence_mode']!='offline' else set())
    def preview(self,args):return {'operation':'save_research','runId':args.get('run_id'),'effect':'Save fetched source evidence excerpts in local Knowledge; original files and model weights stay unchanged.'}
    def remember(self,packet):
        from intelligence_engine import citation_context
        visible=packet.get('sources',[])[:4]
        if self.packet:
            previous=self.packet;visible=list({row['id']:row for row in previous.get('sources',[])+visible}.values())[:10]
            for key in ['queries','discovered','fetched','analyzed']:packet['counts'][key]+=previous['counts'].get(key,0)
            packet['events']=(previous.get('events',[])+packet.get('events',[]))[-64:]
        packet['sources']=visible;packet['context'],packet['contextSourceIds']=citation_context(visible,budget=5500)
        # Every ID retained here is returned in an actual tool observation.
        packet['contextSourceIds']=[row['id'] for row in visible];self.packet=packet;self.engine.knowledge.save_run(packet)
        observation=[]
        for row in visible[-4:]:
            observation.append({key:row.get(key) for key in ['id','title','url','page','sourceType']}|{'excerpt':row.get('excerpt','')[:650]})
        return {'runId':packet['id'],'state':packet['state'],'sources':observation,'counts':packet['counts'],'errors':packet.get('errors',[]),'scope':packet.get('providerBreadth','local knowledge')}
    def call(self,tool,args,cancel,approved=False):
        if tool not in self.available():raise PermissionError('This intelligence tool is unavailable in the current permission mode.')
        if tool=='search_knowledge':return self.remember(self.engine.prepare(args['query'],mode='offline',project=self.project,chat=self.chat,cancel=cancel))
        if tool=='save_research':
            if not approved:raise PermissionError('Saving research requires explicit approval.')
            return self.engine.knowledge.retain_research(args['run_id'],self.project,self.engine.config['research_retention_days'])
        query=args['query']
        query_key=' '.join(query.casefold().split())
        if query_key in self.completed_queries:return dict(self.completed_queries[query_key],alreadyRetrieved=True,networkRequestsThisCall=0)
        allowed=set(tokens(self.prompt))
        if self.packet:
            for source in self.packet.get('sources',[]):
                if source.get('fetchStatus')=='FETCHED' and source.get('sourceType') not in {'document','research'}:allowed.update(tokens(source.get('title','')))
        if not set(tokens(query))<=allowed:raise PermissionError('A tool-generated query contains information outside the approved request/public source titles. Submit that query explicitly; private document text was not sent.')
        remaining_queries=self.engine.config['research_max_queries']-self.query_used;remaining_pages=self.engine.config['research_max_pages']-self.pages_used
        if remaining_queries<=0 or remaining_pages<=0:raise RuntimeError('This Agent request exhausted its approved research budget. Use the observed evidence or submit a new request.')
        original=dict(self.engine.config);self.engine.config.update(research_max_queries=remaining_queries,research_max_pages=remaining_pages)
        try:packet=self.engine.prepare(query,project=self.project,chat=self.chat,grant=NetworkGrant.issue(self.grant.request_id,query),cancel=cancel,emit=self.emit)
        except BaseException:
            self.query_used+=remaining_queries;self.pages_used+=remaining_pages;raise
        finally:self.engine.config=original
        self.query_used+=packet['counts']['queries'];self.pages_used+=packet['counts']['fetched']
        value=self.remember(packet);self.completed_queries[query_key]=value;return value
    def complete(self,answer):return self.engine.complete(self.packet,answer)[0] if self.packet else answer
