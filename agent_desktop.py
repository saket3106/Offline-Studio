"""Qt adapter for the in-application local agent. All inference is off the GUI thread."""
import asyncio
import json
import os
import sqlite3
import tempfile
import re
from pathlib import Path
import time
from PySide6.QtCore import QObject,QThread,Signal,Slot,Qt
from PySide6.QtWidgets import QFileDialog,QSplitter
from PySide6.QtGui import QPalette,QColor
from agent_mcp import sdk_ready,SDK_VERSION
from agent_runtime import AgentRuntime,AgentTaskStore,LocalAgentModel
from agent_workspace import WorkspaceAccess


class AgentWorker(QThread):
    activity=Signal(str)
    def __init__(self,backend,root,protected,prompt,parent=None,resources=None):
        super().__init__(parent);self.backend=backend;self.root=root;self.protected=protected;self.prompt=prompt
        self.runtime=None;self.answer='';self.cancelled=False;self.error='';self.chat=backend.current;self.started=time.monotonic();self.model_identity={}
        self.resources=resources;self.files=[];self.evidence=[];self.visual_evidence=[]
        self.network_grant=None;self.intelligence_config={};self.project_id=''
    def cancel(self):
        self.cancelled=True
        if self.runtime:self.runtime.cancel()
    def run(self):
        temporary=None;access=None
        try:
            from agent_resources import AgentSpecialists,AttachmentRegistry
            if not self.root:temporary=tempfile.TemporaryDirectory(prefix='offlinegpt-agent-readonly-')
            root=self.root or temporary.name
            chat_model = ''
            if hasattr(self.backend, 'store') and hasattr(self.backend.store, 'get_chat_model'):
                chat_model = self.backend.store.get_chat_model(self.chat)
            if not chat_model and hasattr(self.backend, 'model'):
                chat_model = getattr(self.backend, 'model', '')
            if not chat_model and hasattr(self.backend, 'engines') and hasattr(self.backend.engines, 'cfg'):
                chat_model = self.backend.engines.cfg.get('chat_model', '')
            store=AgentTaskStore(self.backend.store.workspace)
            planner=LocalAgentModel(self.backend.engines, model_target=chat_model or None)
            runtime=AgentRuntime(planner,root,store,self.chat,
                         lambda e:self.activity.emit(json.dumps(e,ensure_ascii=False)),protected=self.protected,
                         interpreter=os.environ.get('OFFLINE_GPT_MCP_PYTHON') or None)
            self.runtime=runtime
            access=WorkspaceAccess(root,self.protected)
            def progress(event):
                if not runtime.cancel_event.is_set() and runtime.state not in {'COMPLETED','FAILED','CANCELED','PARTIAL','BUDGET_EXHAUSTED','ANSWERED'}:
                    runtime.emit('SPECIALIST',event.get('summary','Running local specialist'))
            runtime.workspace_authorized=bool(self.root)
            runtime.specialists=AgentSpecialists(self.backend.engines,access,self.resources or AttachmentRegistry(),progress,bool(self.root))
            runtime.resources=(self.resources.public() if self.resources else [])
            from agent_memory import AgentHistory
            # Exclude the current command itself: an agent request is not
            # historical corroboration of whatever it asks the model to claim.
            with self.backend.store.lock:
                row=self.backend.store.con.execute("SELECT id FROM messages WHERE chat_id=? AND role='user' ORDER BY id DESC LIMIT 1",(self.chat,)).fetchone()
            runtime.history=AgentHistory(self.backend.store.recall,row[0] if row else None)
            from intelligence_actions import AgentIntelligence
            runtime.intelligence=AgentIntelligence(self.backend.store.workspace,self.intelligence_config,self.prompt,self.network_grant,self.project_id,self.chat,lambda event:self.activity.emit(json.dumps(event)))
            if self.cancelled:runtime.cancel()
            self.answer=asyncio.run(runtime.run(self.prompt))
            if runtime.state not in {"CANCELED","FAILED"}:self.answer=runtime.intelligence.complete(self.answer)
            self.model_identity=dict(getattr(planner,'completion_identity',{}))
            self.files=runtime.specialists.completed_files;self.evidence=runtime.evidence
            self.visual_evidence=runtime.specialists.visual_evidence
        except Exception as exc:
            self.error=str(exc)[:1000]
            if self.runtime:self.runtime.state='FAILED'
            self.answer='Agent runtime stopped: '+self.error+'. Inspect any separate artifacts before retrying; no operation will be replayed automatically.'
        finally:
            if access:access.close()
            if temporary:temporary.cleanup()


class DesktopAgentController(QObject):
    def __init__(self,bridge,app_dir,data_dir):
        super().__init__(bridge);self.bridge=bridge;self.backend=bridge.backend;self.worker=None;self.root=''
        self.protected=[str(app_dir),str(data_dir)]
        self.final_error=''
        self.attachment_grants={}
        self.attachment_grant_errors={}
    def status(self):
        import agent_mcp
        from agent_mcp import capability_catalog
        vision=self.backend.engines.vision_model_status()
        from agent_mcp import MCPRegistry,TOOL_FIELDS
        selected=self.backend.store.get_chat_model(self.backend.current) if self.backend.current else ''
        selected=selected or self.backend.engines.cfg.get('gpt_oss_gguf','') or (getattr(self.backend,'model','') if self.backend.engines.cfg.get('chat_backend')=='lmstudio' else '')
        counts={'registered':len(TOOL_FIELDS),'enabled':sum(MCPRegistry.get_default().is_tool_enabled(name) for name in TOOL_FIELDS)}
        from intelligence_host import host
        intelligence_state=host(self.backend).state();web_enabled=intelligence_state['settings']['intelligence_mode']!='offline'
        catalog=capability_catalog(vision)
        catalog['research_web']['availability']='permission required for submitted request' if web_enabled else 'unavailable in Offline mode'
        catalog['save_research']['permission']='approve exact local retention';catalog['save_research']['sideEffect']='save fetched evidence excerpts locally'
        return {'selectedModel':str(selected),'toolCounts':counts,'available':sdk_ready(),'sdkVersion':SDK_VERSION,'workspace':self.root,'active':self.worker is not None,
                'capabilityCatalog':catalog,'intelligence':intelligence_state,
                'capabilities':{'transport':'stdio','planner':'bounded local-model JSON actions; acceptance is model-specific',
                                'fileWrites':'new approved copies only','shell':False,'arbitraryPython':False,'networkTools':web_enabled,
                                'nativeImageAgentTools':bool(vision.get('visionAvailable')),'nativeVoiceAgentTools':False},
                'sdkStartupMs':agent_mcp.SDK_STARTUP_MS,
                'reason':agent_mcp.SDK_STARTUP_ERROR or ('' if sdk_ready() else f'Agent Mode needs the reviewed mcp=={SDK_VERSION} dependency set in this build. Ordinary chat remains available.')}
    def pick(self):
        if self.backend.busy or self.worker:return {'ok':False,'error':'Finish or cancel the active task first.'}
        if self.use_native_picker():
            # Native Windows folder picker (owner request): same choose-then-authorize contract.
            start=getattr(self,'_last_workspace_location','') or self.root or str(Path.home()/'Documents')
            chosen=QFileDialog.getExistingDirectory(self.bridge.window,'Choose an Agent workspace',start if Path(start).is_dir() else str(Path.home()),QFileDialog.Option.ShowDirsOnly)
            if not chosen:return {'ok':False,'cancelled':True}
            selected=[chosen]
        else:
            dialog=self.workspace_dialog()
            if dialog.exec()!=QFileDialog.DialogCode.Accepted:return {'ok':False,'cancelled':True}
            selected=dialog.selectedFiles()
        if len(selected)!=1 or not Path(selected[0]).is_dir():return {'ok':False,'error':'Choose one existing folder.'}
        self._last_workspace_location=str(Path(selected[0]).absolute())
        # Choosing is not granting. React shows the exact scope and requires a
        # separate explicit authorization before authorize_workspace runs.
        return {'ok':True,'selectedWorkspace':self._last_workspace_location,'requiresAuthorization':True}
    @staticmethod
    def use_native_picker():
        """Native OS dialog in the real app; the scripted Qt dialog only for headless runs."""
        import os
        return os.name=='nt' and os.environ.get('QT_QPA_PLATFORM','').lower()!='offscreen'
    def workspace_dialog(self):
        parent=self.bridge.window;dialog=QFileDialog(parent,'Choose an Agent workspace')
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog,True)
        dialog.setOption(QFileDialog.Option.ShowDirsOnly,True)
        dialog.setFileMode(QFileDialog.FileMode.Directory);dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        dialog.setLabelText(QFileDialog.DialogLabel.FileName,'Workspace folder:')
        dialog.setLabelText(QFileDialog.DialogLabel.Accept,'Use this folder')
        dialog.setSizeGripEnabled(True);dialog.setViewMode(QFileDialog.ViewMode.Detail)
        start=getattr(self,'_last_workspace_location','') or self.root or str(Path.home()/'Documents')
        if Path(start).is_dir():dialog.setDirectory(start)
        screen=parent.screen();area=screen.availableGeometry();margin=32
        width=min(960,max(640,int(area.width()*.72)),max(240,area.width()-margin))
        height=min(680,max(420,int(area.height()*.76)),max(240,area.height()-margin))
        dialog.setMinimumSize(min(640,width),min(420,height));dialog.resize(width,height)
        for splitter in dialog.findChildren(QSplitter):
            if splitter.orientation()==Qt.Orientation.Horizontal and splitter.count()==2:splitter.setSizes([180,max(320,width-220)])
        settings=getattr(self.bridge,'getSettings',None)
        try:theme=json.loads(settings()).get('theme','dark') if callable(settings) else 'dark'
        except (ValueError,TypeError):theme='dark'
        palette=dialog.palette()
        colors={'Window':'#101013','Base':'#08080a','AlternateBase':'#101013','Button':'#18181c','Text':'#f4f4f5','WindowText':'#f4f4f5','ButtonText':'#f4f4f5','Highlight':'#38383e','HighlightedText':'#ffffff'} if theme!='light' else {'Window':'#ffffff','Base':'#ffffff','AlternateBase':'#f6f7f8','Button':'#f0f1f3','Text':'#18181b','WindowText':'#18181b','ButtonText':'#18181b','Highlight':'#e4e5e8','HighlightedText':'#18181b'}
        for role,color in colors.items():palette.setColor(getattr(QPalette.ColorRole,role),QColor(color))
        dialog.setPalette(palette)
        center=parent.frameGeometry().center();dialog.move(max(area.left()+16,min(center.x()-width//2,area.right()-width-16)),max(area.top()+16,min(center.y()-height//2,area.bottom()-height-16)))
        return dialog
    def authorize_workspace(self,root):
        if self.backend.busy or self.worker:return {'ok':False,'error':'Finish or cancel the active task first.'}
        try:
            if not isinstance(root,str) or not Path(root).is_absolute():raise ValueError('Enter the exact absolute folder to authorize.')
            access=WorkspaceAccess(root,self.protected);access.close();self.root=str(Path(root).resolve())
            return {'ok':True,'workspace':self.root}
        except (OSError,ValueError,PermissionError) as exc:return {'ok':False,'error':str(exc)}
    def grant_attachments(self,paths):
        from agent_resources import AttachmentRegistry
        registry=AttachmentRegistry()
        # An optional Agent intake limit must not break ordinary document chat.
        for path in paths[:4]:
            try:
                for record in registry.register([path],self.backend.current or 'draft','native file selection'):
                    self.attachment_grants[record['path']]=record;self.attachment_grant_errors.pop(record['path'],None)
            except (OSError,ValueError,PermissionError) as exc:self.attachment_grant_errors[str(Path(path).absolute())]=str(exc)
    def start(self,prompt,attachments=None):
        try:
            if getattr(self.backend,'voice_mode_active',False):raise ValueError('End Live Voice before starting Agent Mode; its microphone and model ownership are preserved.')
            if self.worker or self.backend.busy or self.bridge.workspace_jobs:raise ValueError('A local task is already running.')
            if not sdk_ready():raise ValueError(self.status()['reason'])
            if not isinstance(prompt,str) or not prompt.strip() or len(prompt.encode())>8000:raise ValueError('Use a nonempty task under8KiB.')
            if not self.backend.current:self.backend.new_chat()
            from agent_resources import AttachmentRegistry
            def attachment_paths(raw):
                if not raw:return []
                try:value=json.loads(raw) if isinstance(raw,str) and raw.startswith('[') else [raw]
                except ValueError:return []
                return [p for p in value if isinstance(p,str)] if isinstance(value,list) else []
            resources=AttachmentRegistry();current_paths=attachments or []
            if not isinstance(current_paths,list) or len(current_paths)>4 or any(not isinstance(p,str) for p in current_paths):raise ValueError('Choose up to four actual attachment files.')
            prior=[]
            for row in self.backend.store.messages(self.backend.current)[-12:]:prior+=attachment_paths(row[2])
            for path in current_paths:
                absolute=str(Path(path).absolute());grant=self.attachment_grants.get(absolute)
                if grant is None and absolute in self.attachment_grant_errors:raise ValueError(self.attachment_grant_errors[absolute])
                if grant is None and path not in prior:raise PermissionError('Choose or drop this attachment through the application before using it.')
                loaded=resources.register([path],self.backend.current)
                if grant and loaded[0]['sha256']!=grant['sha256']:raise ValueError('Attachment changed after selection. Select it again.')
            if not current_paths and re.search(r'\b(?:image|photo|picture|attachment|uploaded|document|file|it|earlier)\b',prompt,re.I):
                from agent_workspace import READ_TYPES
                existing=[p for p in dict.fromkeys(reversed(prior)) if Path(p).suffix.casefold() in READ_TYPES-{'.sqlite','.sqlite3','.db'}][:4]
                resources.register(existing,self.backend.current,'prior attachment in this conversation')
            from intelligence_host import host
            intelligence_host=host(self.backend);network_grant=intelligence_host.grant(prompt)
            if not self.root and not resources.entries and not network_grant and not intelligence_host.engine().knowledge.documents()['documents']:raise ValueError('Authorize a workspace, attach a supported file, index Knowledge, or enable Web research before starting Agent Mode.')
            if self.root:
                access=WorkspaceAccess(self.root,self.protected);access.close()
            self.bridge._cancel_pending_speech()
            self.backend.cancel_voice_input()
            if self.bridge.speech is not None:self.bridge.speech.shutdown()
            worker=AgentWorker(self.backend,self.root,self.protected,prompt,self,resources)
            worker.network_grant=network_grant;worker.intelligence_config=intelligence_host.engine().config;worker.project_id=intelligence_host.project();self.worker=worker
            worker.activity.connect(self.bridge.event.emit);worker.finished.connect(self.finished)
            self.backend.store.add(self.backend.current,'user',prompt,attachment=json.dumps(current_paths) if current_paths else '',metrics={'agent_resources':resources.public()})
            self.backend.operation_event_id=''
            self.backend.push_messages();self.backend.set_busy(True,'Preparing local Agent task')
            self.backend.active_worker=worker;self.backend.active_thread=worker;self.backend.active_kind='agent'
            worker.start();return {'ok':True,'chatId':self.backend.current}
        except Exception as exc:return {'ok':False,'error':str(exc)}
    def cancel(self):
        if self.worker:self.worker.cancel()
    def approve(self,task,rid,digest,allow):
        worker=self.worker;runtime=worker.runtime if worker else None
        return bool(runtime and runtime.id==task and runtime.broker.decide(task,rid,digest,allow))
    def artifacts(self):
        workspace=self.backend.store.workspace
        try:
            with workspace.lock:
                exists=workspace.con.execute("SELECT 1 FROM sqlite_master WHERE name='agent_artifacts'").fetchone()
            if not exists:return []
            from agent_artifacts import ArtifactJournal
            return ArtifactJournal(workspace).recent(self.backend.current)
        except (sqlite3.DatabaseError,ValueError,KeyError) as exc:return {'ok':False,'error':'Artifact history could not be read: '+str(exc)[:300]}
    def inspect_artifact(self,identifier):
        if self.backend.busy or self.worker:return {'ok':False,'error':'Finish or cancel the current task before inspecting an artifact.'}
        from agent_artifacts import ArtifactJournal
        try:return {'ok':True,**ArtifactJournal(self.backend.store.workspace).inspect(identifier,self.backend.current,self.protected)}
        except (OSError,ValueError,PermissionError,RuntimeError,sqlite3.DatabaseError) as exc:return {'ok':False,'error':str(exc)}
    @Slot()
    def finished(self):
        worker=self.worker
        if worker is None:return
        try:
            self.backend.store.add(worker.chat,'assistant',worker.answer,attachment=json.dumps(worker.files) if worker.files else '',metrics={'agent_task_id':worker.runtime.id if worker.runtime else '',
                                  'agent_state':worker.runtime.state if worker.runtime else 'FAILED',
                                  'model_identity':worker.model_identity,
                                  'agent_evidence':worker.evidence,
                                  'agent_specialist_evidence':worker.visual_evidence,
                                  'agent_traces':getattr(worker.runtime,'traces',[]) if worker.runtime else [],
                                  'duration_seconds':round(time.monotonic()-worker.started,3)})
            self.backend.refresh_history();self.backend.push_messages()
        except Exception as exc:
            self.final_error='Agent result could not be saved: '+str(exc)[:500]
            self.bridge.event.emit(json.dumps({'type':'agentStatus','state':'FAILED','summary':self.final_error,'chatId':worker.chat}))
        finally:
            self.worker=None;self.backend.set_busy(False,'Agent stopped' if worker.error else 'Ready');worker.deleteLater()


    def get_mcp_servers(self):
        from agent_mcp import MCPRegistry
        return {'ok': True, 'servers': MCPRegistry.get_default().get_catalog_manifest()}

    def toggle_mcp_tool(self, tool, enabled):
        from agent_mcp import MCPRegistry
        if self.worker or self.backend.busy:return {'ok':False,'error':'Finish or cancel the current task before changing MCP permissions.'}
        try:MCPRegistry.get_default().toggle_tool(tool, bool(enabled))
        except ValueError as exc:return {'ok':False,'error':str(exc)}
        return {'ok': True, 'tool': tool, 'enabled': bool(enabled)}

    def toggle_mcp_server(self, server, enabled):
        from agent_mcp import MCPRegistry
        if self.worker or self.backend.busy:return {'ok':False,'error':'Finish or cancel the current task before changing MCP permissions.'}
        try:MCPRegistry.get_default().toggle_server(server, bool(enabled))
        except ValueError as exc:return {'ok':False,'error':str(exc)}
        return {'ok': True, 'server': server, 'enabled': bool(enabled)}
