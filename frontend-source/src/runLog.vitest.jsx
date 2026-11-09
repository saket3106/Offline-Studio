import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {RunCard,runLog} from './assistantWorkspace.jsx';
afterEach(cleanup);

const handlers=()=>({onDecide:vi.fn(),onCancel:vi.fn(),onOpenFile:vi.fn()});

describe('assistant execution log and confirmation',()=>{
 it('asks before a confirm-tier step and sends the decision',()=>{
  const h=handlers();
  render(<RunCard run={{id:'r1',request:'turn on gaming mode',status:'awaiting',route:'rules',steps:[{tool:'power_mode',args:{mode:'performance'},risk:'confirm',status:'awaiting'}]}} {...h}/>);
  const card=screen.getByRole('group',{name:'Confirm Power mode'});
  expect(card.textContent).toContain('Needs your OK.');expect(card.textContent).toContain('performance');expect(card.textContent).toContain('Nothing runs until you choose');
  fireEvent.click(screen.getByRole('button',{name:'Allow'}));expect(h.onDecide).toHaveBeenCalledWith('r1',0,true);
  fireEvent.click(screen.getByRole('button',{name:'Skip'}));expect(h.onDecide).toHaveBeenCalledWith('r1',0,false);
  expect(screen.queryByText(/Execution log/)).toBeNull(); // log appears once the run has finished
 });
 it('shows per-step time and a plain-text log when the run is done',()=>{
  const run={id:'r2',request:'open spotify and set volume to 30',status:'done',route:'model',planMs:840,totalMs:1320,
   steps:[{tool:'open_app',args:{name:'spotify'},risk:'low',status:'done',message:'Opened Spotify.',ms:310},{tool:'volume',args:{level:30},risk:'low',status:'error',message:'No audio device.'}]};
  render(<RunCard run={run} {...handlers()}/>);
  expect(document.querySelector('.assistant-step-time').textContent).toBe(' · 310 ms');
  expect(screen.getByText(/Execution log · 1.3 s/)).toBeTruthy();
  const log=runLog(run).split('\n');
  expect(log[0]).toBe('plan  local model · 840 ms');
  expect(log[1]).toBe('01  open_app(name="spotify")  done · 310 ms  → Opened Spotify.');
  expect(log[2]).toBe('02  volume(level=30)  error  → No audio device.');
  expect(log[3]).toBe('total 1.3 s · done');
 });
});
