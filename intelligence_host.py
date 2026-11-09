"""GUI-owned permission and lifecycle adapter for the existing Qt bridge and workers."""
from pathlib import Path
import hashlib,json,re,threading,uuid
from PySide6.QtCore import QObject,QThread,Signal,Slot,QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog,QMessageBox
from intelligence_engine import IntelligenceEngine,NetworkGrant,settings,needs_web,DEFAULTS
from intelligence_actions import regular_path


def ask_on_top(parent,title,message,always=False):
    """Yes/No permission prompt that is raised and focused above the main window.
    A plain QMessageBox could open behind the app, leaving a turn waiting unseen.
    always=True adds "Always allow" (QMessageBox.YesToAll) so a user who chose Web mode is not asked every turn."""
    from PySide6.QtCore import Qt
    buttons=QMessageBox.Yes|QMessageBox.No|(QMessageBox.YesToAll if always else QMessageBox.NoButton)
    box=QMessageBox(QMessageBox.Icon.Question,title,message,buttons,parent)
    if always:box.button(QMessageBox.YesToAll).setText('Always allow');box.button(QMessageBox.Yes).setText('Allow once')
    box.setDefaultButton(QMessageBox.No);box.setObjectName('studio-permission-dialog');box.setAccessibleName(title)
    box.setWindowModality(Qt.WindowModality.ApplicationModal)
    box.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,True)
    if parent is not None:
        try:parent.raise_();parent.activateWindow()
        except Exception:pass
    box.show();box.raise_();box.activateWindow()
    box.exec()
    clicked=box.clickedButton()
    if always and clicked is box.button(QMessageBox.YesToAll):return QMessageBox.YesToAll
    return QMessageBox.Yes if clicked is box.button(QMessageBox.Yes) else QMessageBox.No


class PreparationWorker(QObject):
    done=Signal(object);failed=Signal(str);progress=Signal(str)
    def __init__(self,workspace,config,text,chat,project,grant,engines=None):
        super().__init__();self.workspace=workspace;self.config=config;self.text=text;self.chat_id=chat;self.project=project;self.grant=grant;self.cancel_event=threading.Event()
        self.engines=engines
    def cancel(self):self.cancel_event.set()
    def run(self):
        acquired=False
        try:
            if self.engines:
                while not self.engines.resource_lock.acquire(timeout=.2):
                    if self.cancel_event.is_set():raise InterruptedError('Research cancelled while waiting for local resources.')
                acquired=True
            packet=IntelligenceEngine(self.workspace,self.config).prepare(self.text,project=self.project,chat=self.chat_id,grant=self.grant,cancel=self.cancel_event,emit=lambda event:self.progress.emit(json.dumps(event)))
            if acquired:self.engines.resource_lock.release();acquired=False
            self.done.emit(packet)
        except Exception as exc:self.failed.emit(str(exc))
        finally:
            if acquired:self.engines.resource_lock.release()


class IntelligenceHost(QObject):
    def __init__(self,bridge):
        super().__init__(bridge);self.bridge=bridge;self.backend=bridge.backend;self.path_grants={}
    def engine(self):
        from integrated_runtime import load_config
        return IntelligenceEngine(self.backend.store.workspace,load_config())
    def project(self):
        try:
            context=self.backend.store.recall.project_context(self.backend.current) or {};return str(context.get('id') or context.get('projectId') or '')
        except Exception:return ''
    def state(self):
        engine=self.engine();value=engine.health()
        try:
            from reference_workflow import reference_capabilities
            cli=self.backend.engines.image_path('sd_cli');flags=self.backend.engines.image_capabilities(cli)
            value['referenceConditioning']=reference_capabilities(engine.config,'',flags)
        except Exception as exc:value['referenceConditioning']={'referenceEditing':'UNAVAILABLE_OR_NOT_PROBED','error':str(exc)[:300],'inferenceVerified':False}
        return value
    def probe_provider(self,query):
        engine=self.engine();cfg=engine.config
        if cfg['intelligence_mode']=='offline':raise PermissionError('Switch to Web or Smart Hybrid before testing a network provider. Strict Offline never connects.')
        if cfg['research_provider']=='none':raise ValueError('Choose a discovery provider before testing connectivity.')
        query=str(query or '').strip()[:300] or 'Offline Studio research connectivity test'
        capabilities=engine.health()['providerCapabilities']
        if QMessageBox.question(self.bridge.window,'Test discovery provider',f"Send this test query to the configured provider?\n\n{query}\n\nProvider: {cfg['research_provider']}\nScope: {capabilities.get('breadth','')}\n\nThe query contains no local documents or chat history.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:raise PermissionError('Provider test cancelled.')
        return engine.probe_provider(query,NetworkGrant.issue(uuid.uuid4().hex,query))
    def save_settings(self,raw):
        from integrated_runtime import load_config,save_config
        args=json.loads(raw);allowed={key:value for key,value in args.items() if key in DEFAULTS};current=load_config();validated=settings({**current,**allowed});save_config({**current,**validated})
        value=self.state();self.backend.emit_frontend({'type':'intelligenceSettings','value':value});return value
    def grant(self,query):
        engine=self.engine();cfg=engine.config
        if not needs_web(query,cfg['intelligence_mode']):return None
        if cfg['research_permission']!='always':
            message=('Allow public web research for this submitted request? Only the displayed request is used for search; local documents and chat history are not appended.\n\n'+str(query)[:1200]+f"\n\nProvider: {cfg['research_provider']} · up to {cfg['research_max_queries']} queries / {cfg['research_max_pages']} pages / {cfg['research_timeout']} seconds.")
            answer=ask_on_top(self.bridge.window,'Allow web research',message+'\n\n"Always allow" stops this question for Web and Smart Hybrid; change it in Settings > Internet & privacy.',always=True)
            if answer==QMessageBox.YesToAll:self.save_settings(json.dumps({'research_permission':'always'}))
            elif answer!=QMessageBox.Yes:raise PermissionError('Web search declined. Ask again with “without the web” to answer from what the model knows.')
        return NetworkGrant.issue(uuid.uuid4().hex,query)
    def pick_sources(self,folder=False):
        from workspace_services import SUPPORTED_DOCUMENTS
        paths=[]
        if folder:
            directory=QFileDialog.getExistingDirectory(self.bridge.window,'Authorize a Knowledge folder (bounded import)')
            if not directory:return {'cancelled':True}
            root=Path(directory).absolute()
            for part in [root,*root.parents]:
                if part.is_symlink() or getattr(part,'is_junction',lambda:False)():raise PermissionError('Redirected folders are unavailable.')
            # No unbounded rglob across link/junction directories.
            import os
            for current,dirs,files in os.walk(root,followlinks=False):
                dirs[:]=[name for name in sorted(dirs) if name not in {'.git','node_modules','.venv','__pycache__'} and not (Path(current)/name).is_symlink() and not getattr(Path(current)/name,'is_junction',lambda:False)()]
                for name in sorted(files):
                    path=Path(current)/name
                    if path.suffix.lower() in SUPPORTED_DOCUMENTS and not name.startswith('.') and path.name.lower() not in {'credentials.json','secrets.json','offline_gpt_config.json'}:paths.append(str(regular_path(path)))
                    if len(paths)>=50:break
                if len(paths)>=50:break
        else:paths=QFileDialog.getOpenFileNames(self.bridge.window,'Authorize Knowledge sources','', 'Documents and source files (*.*)')[0]
        paths=[str(regular_path(path)) for path in paths[:50]]
        if not paths:return {'cancelled':True}
        token=uuid.uuid4().hex;self.path_grants[token]=paths
        return {'grant':token,'paths':paths,'boundedAt':50}
    def authorize_action(self,args):
        operation=args.get('operation');args={key:value for key,value in args.items() if not key.startswith('_')}
        if operation=='index':
            selected=self.path_grants.pop(args.pop('grant',''),None)
            if not selected or selected!=args.get('paths'):raise PermissionError('The selected-source authorization is missing or changed.')
            args['_trustedPaths']=selected
        if operation in {'remove','deleteMemory','removeReference'}:
            if QMessageBox.question(self.bridge.window,'Remove local knowledge','Remove this indexed source, memory or saved reference record? Original files, cached reference images and chats are preserved.',QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:raise PermissionError('Removal cancelled.')
        if operation in {'research','providerProbe','discoverImages'}:
            query=str(args.get('query') or ('Royal Enfield Hunter 350' if operation=='providerProbe' else ''))
            if not query.strip():raise ValueError('Enter a research or reference query.')
            grant=self.grant(query)
            if grant:args['_networkGrant']=grant.__dict__
            args['_chatId']=self.backend.current
            if operation!='research' and not grant:raise PermissionError('Switch to Web or Hybrid mode before testing or searching a provider.')
        if operation=='subjectComposite':
            selected=self.path_grants.pop(args.pop('backgroundGrant',''),None)
            if not selected or len(selected)!=1:raise PermissionError('Choose one background through the native picker first.')
            args['_trustedBackground']=selected[0]
        if operation=='downloadReference':
            if self.engine().config['intelligence_mode']=='offline':raise PermissionError('Strict Offline mode blocks downloading web references.')
            refs=self.engine().reference_candidates(args['runId']);selected=refs[int(args['index'])];target=selected.get('downloadUrl') or selected['url']
            if QMessageBox.question(self.bridge.window,'Download selected reference',f"Download this image as a local reference?\n\n{target}\n\nLicense: {selected.get('license') or 'Not established'}\nSource: {selected.get('sourceUrl') or target}\n\nInspect source rights before reuse. Downloading stores bytes locally; generation conditions only when you attach the saved image to the native edit path.",QMessageBox.Yes|QMessageBox.No,QMessageBox.No)!=QMessageBox.Yes:raise PermissionError('Reference download cancelled.')
            args['_networkGrant']=NetworkGrant.issue(uuid.uuid4().hex,target).__dict__
        return args
    def start(self,text):
        from integrated_runtime import load_config
        cfg=load_config();engine=self.engine();mode=engine.config['intelligence_mode']
        # Live Voice answers go straight to the local model in Offline mode:
        # no research card and no retrieval latency before the first audio.
        if mode=='offline' and getattr(self.backend,'voice_mode_active',False):return False
        if mode=='offline' and not engine.knowledge.documents()['chunks'] and not engine.knowledge.memory('list',{'projectId':self.project()}):return False
        if re.fullmatch(r'\s*(?:hi|hello|hey|thanks)[.!? ]*',text,re.I):return False
        grant=self.grant(text) if needs_web(text,mode) else None
        backend=self.backend;backend.operation_event_id=uuid.uuid4().hex;backend.operation_bubble=None;backend._intelligence_packet=None
        worker=PreparationWorker(backend.store.workspace,cfg,text,backend.current,self.project(),grant,backend.engines);thread=QThread();worker.moveToThread(thread);thread.started.connect(worker.run);worker.progress.connect(self.progress)
        backend.set_busy(True,'Preparing research and local knowledge…');backend.register_worker('intelligence',thread,worker,[(worker.done,self.prepared),(worker.failed,self.failed)]);thread.start();return True
    @Slot(str)
    def progress(self,raw):
        worker=self.sender()
        if worker is self.backend.active_worker and worker.chat_id==self.backend.current:self.backend.emit_frontend(json.loads(raw))
    @Slot(object)
    def prepared(self,packet):
        worker=self.sender();backend=self.backend
        if worker is not backend.active_worker or worker.chat_id!=backend.current:return
        if worker.cancel_event.is_set() or backend.stopping:self.failed('Research cancelled.');return
        backend.store.workspace.finish(worker.operation_event_id,'success');backend._intelligence_packet=packet;backend.emit_frontend({'type':'intelligenceResult','chatId':backend.current,'packet':public_packet(packet)})
        backend._intelligence_resume=True
        try:
            from knowledge_engine import LocalEmbedding
            LocalEmbedding.clear_cache()
            backend.answer(worker.text)
        finally:backend._intelligence_resume=False
    @Slot(str)
    def failed(self,error):
        worker=self.sender();backend=self.backend
        if worker is not backend.active_worker or worker.chat_id!=backend.current:return
        cancelled=worker.cancel_event.is_set();backend.store.workspace.finish(worker.operation_event_id,'cancelled' if cancelled else 'failure')
        if not cancelled and not backend.stopping:
            # Research is optional context. Never show an internal pipeline error
            # as the assistant's answer: log it, keep a quiet notice, and answer
            # with the local model alone.
            import logging
            logging.getLogger(__name__).warning('Research preparation failed; answering locally: %s',error)
            backend._intelligence_packet=None
            backend.emit_frontend({'type':'intelligenceNotice','chatId':backend.current,'message':'Research was unavailable for this message; answered with the local model only.','detail':str(error)[:300]})
            backend._intelligence_resume=True
            try:backend.answer(worker.text)
            finally:backend._intelligence_resume=False
            return
        backend.set_busy(False,'Cancelled')
        backend.store.add(backend.current,'assistant','Research cancelled.',metrics={'intelligence_error':True,'model_calls':0});backend.push_messages();backend.emit_frontend({'type':'intelligenceResult','chatId':backend.current,'packet':{'state':'CANCELLED','errors':[],'counts':{},'sources':[]}})
        live=getattr(backend,'live_voice_session',None)
        if live and live.active:live.fail(error)
    def open_source(self,run_id,source_id):
        row=next((row for row in self.engine().knowledge.research() if row['id']==run_id),None)
        source=next((source for source in (row or {}).get('packet',{}).get('sources',[]) if source['id']==source_id),None)
        if not source:raise ValueError('Source is not part of this recorded research.')
        if source.get('url'):
            from research_network import canonical_url
            return QDesktopServices.openUrl(QUrl(canonical_url(source['url'])))
        if source.get('documentId'):return self.bridge.openDocumentSource(source['documentId'],int(source.get('page') or 1))
        raise ValueError('Source cannot be opened.')
    def start_reference_image(self,ident,prompt,project=''):
        from reference_workflow import ReferenceStore
        from integrated_runtime import physical_memory_status
        backend=self.backend
        if backend.busy or any(i not in self.bridge.workspace_finished_ids for i in self.bridge.workspace_jobs):raise RuntimeError('Finish or stop the active task first.')
        if getattr(backend,'voice_mode_active',False):raise RuntimeError('End Live Voice before acquiring the image engine.')
        reference=ReferenceStore(backend.store.workspace).get(ident,project)
        if not str(prompt).strip() or len(prompt)>8000:raise ValueError('Enter an editing prompt under 8,000 characters.')
        if physical_memory_status().get('available',0)<4*1024**3:raise RuntimeError('Native reference generation is waiting for 4 GiB available RAM; CPU subject composition remains available.')
        cli=backend.engines.image_path('sd_cli');flags=backend.engines.image_capabilities(cli)
        if not {'-r','--ref-image'}&set(flags):raise RuntimeError('The installed image backend did not expose a native reference input.')
        if not backend.current:backend.new_chat()
        backend.store.add(backend.current,'user',prompt,attachment=reference['path']);backend.push_messages();backend._selected_reference_record=reference
        backend.set_busy(True,'Preparing actual reference image input…')
        backend.image('edit_image',prompt,reference['path'],prompt_prepared=True,source_prompt=prompt,planned_prompt=prompt)
        return {'started':True,'method':'FLUX2_NATIVE_REFERENCE_ARGUMENT','referenceSha256':reference['imageHash'],'inferenceVerified':False}


def public_packet(packet):return {key:value for key,value in packet.items() if key not in {'context','memories'}}


def host(backend):
    bridge=getattr(backend,'frontend_bridge',None)
    if bridge is None:return None
    if not hasattr(bridge,'_intelligence_host'):bridge._intelligence_host=IntelligenceHost(bridge)
    return bridge._intelligence_host


def begin(backend,text):
    if getattr(backend,'_intelligence_resume',False):return False
    packet=getattr(backend,'_intelligence_packet',None)
    if packet and packet.get('chatId')==backend.current and packet.get('requestDigest')==hashlib.sha256(str(text).encode()).hexdigest():return False
    current=host(backend)
    if current is None:return False
    try:return current.start(text)
    except Exception as exc:
        backend.set_busy(False,'Research needs attention');backend.store.add(backend.current,'assistant',str(exc),metrics={'model_calls':0});backend.push_messages()
        live=getattr(backend,'live_voice_session',None)
        if live and live.active:live.fail(str(exc))
        return True


def context(backend):
    packet=getattr(backend,'_intelligence_packet',None)
    return packet['context'] if packet and packet.get('chatId')==backend.current else ''


def finish(backend,text):
    packet=getattr(backend,'_intelligence_packet',None)
    if not packet or packet.get('chatId')!=backend.current:return text
    text,packet=host(backend).engine().complete(packet,text);backend._intelligence_packet=packet;backend.emit_frontend({'type':'intelligenceResult','chatId':backend.current,'packet':public_packet(packet)});return text
