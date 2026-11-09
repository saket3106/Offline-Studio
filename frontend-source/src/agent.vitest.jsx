import React from 'react';
import {test,expect,vi} from 'vitest';
import {render,screen,fireEvent,act} from '@testing-library/react';
import {AgentWorkspacePanel,AgentExecutionTraceView} from './agent.jsx';
globalThis.IS_REACT_ACT_ENVIRONMENT=true;

function setup() {
 let receive;const bridge={event:{connect:fn=>{receive=fn;},disconnect:()=>{}},cancelAgent:vi.fn()};
 const request=vi.fn(async()=>[]);const onInfo=vi.fn();
 const props={bridge,request,onInfo,chatId:'one',info:{available:true},onDisable:()=>{}};
 return {props,send:event=>act(()=>receive(JSON.stringify({type:'agentStatus',chatId:'one',taskId:'task',...event})))};
}
const approval=id=>({requestId:id,digest:'a'.repeat(64),expiresInSeconds:90,tool:'run_python_tests',preview:{target:'test_demo.py',effects:'Execute reviewed code.',executionWarning:'NOT A SECURITY SANDBOX. Code runs with your permissions.',command:['runtime','unittest','test_demo.py'],cwd:'isolated snapshot',runtime:'packaged worker',planSha256:'b'.repeat(64),timeoutSeconds:8,files:[{path:'test_demo.py',sha256:'c'.repeat(64),bytes:120}]}});

test('test execution shows code identities and requires a trust acknowledgment',async()=>{
 const env=setup();render(<AgentWorkspacePanel {...env.props}/>);
 await env.send({state:'AWAITING_APPROVAL',approval:approval('first')});
 expect(screen.getByRole('button',{name:'Allow once'}).disabled).toBe(true);
 expect(screen.getByText(/NOT A SECURITY SANDBOX/)).toBeTruthy();
 expect(screen.getByText('packaged worker')).toBeTruthy();
 fireEvent.click(screen.getByRole('checkbox'));
 expect(screen.getByRole('button',{name:'Allow once'}).disabled).toBe(false);
});

test('an older approval reply cannot dismiss a newer request',async()=>{
 const env=setup();let resolve;env.props.request.mockImplementation(async(name)=>name==='approveAgent'?new Promise(done=>{resolve=done;}):[]);
 render(<AgentWorkspacePanel {...env.props}/>);
 await env.send({state:'AWAITING_APPROVAL',approval:approval('first')});
 fireEvent.click(screen.getByRole('checkbox'));fireEvent.click(screen.getByRole('button',{name:'Allow once'}));
 await env.send({state:'AWAITING_APPROVAL',approval:approval('second')});
 await act(async()=>resolve({ok:false}));
 expect(screen.getByRole('dialog')).toBeTruthy();
 expect(screen.getByRole('button',{name:'Allow once'}).disabled).toBe(true);
 expect(screen.queryByText('This approval expired or changed. No operation was authorized.')).toBeNull();
});

test('interrupted tasks refresh the desktop status and do not offer ongoing cancellation',async()=>{
 const env=setup();render(<AgentWorkspacePanel {...env.props}/>);
 await env.send({state:'INTERRUPTED',summary:'Task interrupted'});
 expect(env.props.request).toHaveBeenCalledWith('getAgentStatus');
 expect(screen.queryByRole('button',{name:'Cancel'})).toBeNull();
 expect(screen.getByText('Interrupted')).toBeTruthy();
});

test('unknown or interrupted trace statuses do not render a success marker',()=>{
 const {container}=render(<AgentExecutionTraceView traces={[{tool:'test',status:'cancelled'},{tool:'read',status:'success'},{tool:'write',status:'failed'}]}/>);
 expect(container.querySelectorAll('.trace-success').length).toBe(1);
 expect(container.querySelectorAll('.trace-error').length).toBe(1);
 expect(container.querySelectorAll('.trace-unknown').length).toBe(1);
});
