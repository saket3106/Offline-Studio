"""Bounded explicit MCP checks; source-agent additionally requires native consent.

No user workspace, production profile, microphone or GUI is used. This file is
not discovered as a routine unit test and never starts a model at import.
"""
from pathlib import Path
import argparse,asyncio,json,os,secrets,sys,time
S=Path(__file__).resolve().parents[1];sys.path.insert(0,str(S))
F=S.parent;V=F/'Documentation/VoiceRepair20261026';R=F/'Recovery/VoiceRepair20261026'
from agent_permissions import canonical

async def check(kind):
    from mcp import Client
    from mcp.client.stdio import StdioServerParameters
    root=R/'master-mcp-workspace';root.mkdir(exist_ok=True)
    source=root/'evidence.txt'
    if not source.exists():source.write_text('Delivery status: delayed by two days. Reference: ORCHID-715.\n',encoding='utf-8')
    assert source.read_text().startswith('Delivery status:')
    import fitz
    from PIL import Image
    pdf=root/'evidence.pdf';picture=root/'evidence.png'
    if not pdf.exists():
        doc=fitz.open();page=doc.new_page();page.insert_text((72,72),'Physical PDF page evidence: CEDAR-357.');doc.save(pdf);doc.close()
    if not picture.exists():Image.new('RGB',(13,17),'blue').save(picture)
    profile=R/'master-mcp-profile';profile.mkdir(exist_ok=True)
    if kind=='installed':executable=F/'Application/Offline GPT.exe';args=['--offline-mcp-server',str(root),canonical([])]
    else:
        executable=Path(sys.executable).with_name('pythonw.exe')
        args=['-I','-B',str(S/'agent_mcp.py'),'--serve',str(root),canonical([])]
    assert executable.is_file()
    env={'OFFLINEGPT_MCP_KEY':secrets.token_hex(32),'OFFLINE_GPT_DATA_DIR':str(profile),'PYTHONDONTWRITEBYTECODE':'1','OTEL_SDK_DISABLED':'true','OTEL_TRACES_EXPORTER':'none','OTEL_METRICS_EXPORTER':'none','OTEL_LOGS_EXPORTER':'none'}
    observations=[];start=time.perf_counter();error=None
    try:
        async with asyncio.timeout(15):
            async with Client(StdioServerParameters(command=str(executable),args=args,env=env,cwd=str(executable.parent)),read_timeout_seconds=8) as client:
                tools=await client.list_tools();assert {x.name for x in tools.tools}=={'workspace_operation'}
                operations=[('calculate',{'expression':'19*23'}),('read_local_file',{'path':'evidence.txt'}),('search_workspace',{'query':'ORCHID-715'}),('extract_pdf_text',{'path':'evidence.pdf'}),('inspect_file_metadata',{'path':'evidence.png'}),('read_local_file',{'path':'../outside.txt'}),('search_workspace',{'path':'Downloads'}),('unknown_file_search',{}),('write_local_file',{'path':'must-not-exist.txt','content':'unapproved'})]
                for operation,arguments in operations:
                    response=await client.call_tool('workspace_operation',{'operation':operation,'arguments':arguments,'approval':''})
                    value=response.structured_content;observations.append({'operation':operation,'isError':response.is_error,'result':value,'errorText':''.join(getattr(x,'text','') for x in response.content)[:500] if response.is_error else ''})
                    if operation=='calculate':assert not response.is_error and value.get('value')==437
                    elif operation=='read_local_file' and arguments['path']=='evidence.txt':assert not response.is_error and 'ORCHID-715' in value.get('text','')
                    elif operation=='search_workspace' and 'query' in arguments:assert not response.is_error and 'ORCHID-715' in json.dumps(value)
                    elif operation=='extract_pdf_text':assert not response.is_error and 'CEDAR-357' in json.dumps(value)
                    elif operation=='inspect_file_metadata':
                        import hashlib
                        assert not response.is_error and value.get('bytes')==picture.stat().st_size and value.get('sha256')==hashlib.sha256(picture.read_bytes()).hexdigest()
                    else:assert response.is_error and not (root/'must-not-exist.txt').exists()
    except Exception as exc:error=repr(exc)
    result={'scope':'Real installed windowed EXE stdio' if kind=='installed' else 'Canonical source executed by retained pythonw.exe with real inherited pipes','kind':kind,'status':'PASS' if not error else 'FAIL','error':error,'seconds':time.perf_counter()-start,'observations':observations,'modelCalls':0,'microphoneCalls':0,'productionDataUsed':False}
    state_path=V/'MASTER_STATE.json';state=json.loads(state_path.read_text());state.setdefault('windowedMcpChecks',[]).append(result);state_path.write_text(json.dumps(state,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    return result

def check_agent():
    import threading,hashlib,psutil,re
    sys.path.insert(0,str(F/'Documentation'))
    from native_guard_20261026 import Guard
    profile=R/'master-agent-profile';profile.mkdir(exist_ok=True)
    os.environ.update(OFFLINE_GPT_DATA_DIR=str(profile),OFFLINE_GPT_CAPTURE_FITTED_PROMPTS='0',OFFLINE_GPT_SAVE_TRAINING_CANDIDATES='0')
    from integrated_runtime import EngineManager
    from agent_runtime import AgentRuntime,AgentTaskStore,LocalAgentModel
    import app
    workspace=R/'master-mcp-workspace'
    fixture=workspace/'evidence.txt';before=hashlib.sha256(fixture.read_bytes()).hexdigest()
    result={'scope':'Genuine Qwen3-4B canonical-source Agent with real stdio MCP and isolated SQLite; not installed-EXE Agent acceptance','events':[],'errors':[]}
    manager=store=runtime=guard=None;thread=None;started=time.monotonic()
    try:
        guard=Guard();guard.preflight(4*2**30)
        model=F/'Models/Chat/Qwen3-4B-Q4_K_M.gguf';assert model.is_file()
        manager=EngineManager();manager.log_dir=profile/'logs';manager.log_dir.mkdir(exist_ok=True)
        manager.cfg.update(chat_backend='bundled',gpt_oss_gguf=str(model),chat_context=4096,chat_gpu='auto',chat_gpu_layers=-1,hardware_profile='balanced',model_lifecycle_mode='fast',capture_fitted_prompts=False)
        store=app.Store();chat=store.new_chat('Synthetic master Agent acceptance')
        planner=LocalAgentModel(manager,str(model));answers=[]
        runtime=AgentRuntime(planner,str(workspace),AgentTaskStore(store.workspace),chat,result['events'].append,steps=6,seconds=100,interpreter=sys.executable)
        def run():
            try:answers.append(asyncio.run(runtime.run('Analyze evidence.txt in this approved workspace. Report the delivery status, the number of days of delay, and the reference identifier. Cite the actual file. Do not modify files.')))
            except Exception as exc:result['errors'].append(repr(exc))
        thread=threading.Thread(target=run,name='OfflineGPT-bounded-agent-fixture');thread.start()
        while thread.is_alive():
            guard.observe();assert time.monotonic()-started<115,'Native Agent fixture time bound';time.sleep(.25)
        thread.join()
        answer=answers[-1] if answers else '';lower=answer.casefold()
        checks={'realContentRead':any(t['tool'] in {'read_local_file','inspect_workspace'} and t['status']=='completed' for t in runtime.traces),
                'deliveryStatus':'delay' in lower,'days':bool(re.search(r'\b(?:two|2)[ -]days?\b',lower)),'reference':'ORCHID-715' in answer,
                'source':'evidence.txt' in answer,'noWriteApproval':not any(e['state']=='AWAITING_APPROVAL' for e in result['events']),
                'fixtureUnchanged':hashlib.sha256(fixture.read_bytes()).hexdigest()==before}
        result.update(answer=answer,state=runtime.state,checks=checks,traces=runtime.traces,evidence=runtime.evidence,identity=planner.completion_identity,diagnostics=dict(getattr(manager.runtime,'last_generation_diagnostics',{})))
        result['status']='PASS' if all(checks.values()) and runtime.state in {'COMPLETED','ANSWERED'} and not result['errors'] else 'FAIL'
    except Exception as exc:
        result['status']='STOPPED';result['errors'].append(repr(exc))
    finally:
        if thread and thread.is_alive():
            runtime.cancel();thread.join(10)
        if manager:manager.shutdown()
        if guard:guard.cleanup()
        if thread and thread.is_alive():thread.join(5)
        if store and not (thread and thread.is_alive()):store.con.close()
        result['seconds']=time.monotonic()-started
        result['samples']=guard.samples if guard else []
        result['remainingFixtureThread']=bool(thread and thread.is_alive())
        result['remainingOwnedProcesses']=[]
        if guard:
            for pid,birth in guard.owned.items():
                try:
                    p=psutil.Process(pid)
                    if p.create_time()==birth and p.is_running():result['remainingOwnedProcesses'].append(pid)
                except psutil.Error:pass
        if result['remainingFixtureThread'] or result['remainingOwnedProcesses']:result['status']='FAIL'
        state_path=V/'MASTER_STATE.json';state=json.loads(state_path.read_text());state.setdefault('nativeAgentChecks',[]).append(result);state_path.write_text(json.dumps(state,indent=2),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k not in {'events','samples'}},indent=2))
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--kind',choices=['installed','source-windowed','source-agent'],required=True);args=parser.parse_args()
    result=check_agent() if args.kind=='source-agent' else asyncio.run(check(args.kind));raise SystemExit(0 if result['status']=='PASS' else 1)
