import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {AssistantWorkspace,mergeRun} from './assistantWorkspace.jsx';
afterEach(cleanup);

const props=(over={})=>({runs:[],onCommand:vi.fn(),onQuick:vi.fn(async()=>({ok:true,message:'Next track.'})),onDecide:vi.fn(),onCancel:vi.fn(),onOpenFile:vi.fn(),
 settings:{autoLowRisk:true},onSettings:vi.fn(),voiceActive:false,onToggleVoice:vi.fn(),cards:[],cardHandlers:{onExecute:vi.fn(),onCancel:vi.fn(),onDismiss:vi.fn(),onSaveEmail:vi.fn()},...over});

describe('assistant workspace',()=>{
 it('runs a typed command and a suggestion',()=>{
  const p=props();render(<AssistantWorkspace {...p}/>);
  fireEvent.change(screen.getByLabelText('Tell the assistant what to do'),{target:{value:'volume 30'}});
  fireEvent.click(screen.getByRole('button',{name:'Run'}));
  expect(p.onCommand).toHaveBeenCalledWith('volume 30');
  fireEvent.click(screen.getByRole('button',{name:'Set a timer for 10 minutes'}));
  expect(p.onCommand).toHaveBeenCalledWith('Set a timer for 10 minutes');
 });
 it('quick tiles report their result',async()=>{
  const p=props();render(<AssistantWorkspace {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:/Next/}));
  expect(p.onQuick).toHaveBeenCalledWith('media',{action:'next'});
  expect(await screen.findByText('Next track.')).toBeTruthy();
 });
 it('a waiting step offers Allow and Skip; found files open on click',()=>{
  const run={id:'r',request:'lock my pc',status:'awaiting',route:'rules',steps:[{tool:'lock_pc',args:{},risk:'confirm',status:'awaiting',message:''},
   {tool:'find_files',args:{query:'resume'},risk:'low',status:'done',message:'Found 1 file(s).',files:['C:\\Users\\me\\Documents\\resume.pdf']}]};
  const p=props({runs:[run]});render(<AssistantWorkspace {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Allow'}));expect(p.onDecide).toHaveBeenCalledWith('r',0,true);
  fireEvent.click(screen.getByRole('button',{name:'Skip'}));expect(p.onDecide).toHaveBeenCalledWith('r',0,false);
  fireEvent.click(screen.getByRole('button',{name:'resume.pdf'}));expect(p.onOpenFile).toHaveBeenCalledWith('C:\\Users\\me\\Documents\\resume.pdf');
 });
 it('auto-run toggle saves and runs merge newest first',()=>{
  const p=props();render(<AssistantWorkspace {...p}/>);
  fireEvent.click(screen.getByRole('checkbox'));expect(p.onSettings).toHaveBeenCalledWith({autoLowRisk:false});
  const merged=mergeRun(mergeRun([], {id:'a',status:'done'}),{id:'b',status:'running'});
  expect(merged.map(r=>r.id)).toEqual(['b','a']);
  expect(mergeRun(merged,{id:'a',status:'error'})[1].status).toBe('error');
 });
});
