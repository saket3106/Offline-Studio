import React from 'react';
import {afterEach,describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {ReferenceControls} from './ReferenceControls.jsx';

afterEach(cleanup);
const reference={id:'saved-real-id',width:800,height:600,state:'saved'};
describe('Reference controls',()=>{
 it('passes the saved identity and project through native reference generation',async()=>{
  const bridge={startReferenceImage:vi.fn((id,prompt,project,cb)=>cb(JSON.stringify({ok:true,value:{started:true}})))};
  render(<ReferenceControls bridge={bridge} reference={reference} project="project-a"/>);
  fireEvent.click(screen.getByText('Generate with actual FLUX reference'));
  await screen.findByText(/Started native reference generation/);
  expect(bridge.startReferenceImage.mock.calls[0][0]).toBe(reference.id);
  expect(bridge.startReferenceImage.mock.calls[0][2]).toBe('project-a');
 });
 it('requires a native background grant before composition and displays backend errors',async()=>{
  const bridge={pickKnowledgeSources:vi.fn((folder,cb)=>cb(JSON.stringify({ok:false,error:'Picker denied'})))};
  render(<ReferenceControls bridge={bridge} reference={reference}/>);
  expect(screen.getByText('Composite selected pixels').disabled).toBe(true);
  fireEvent.click(screen.getByText('Choose background image'));
  await screen.findByText('Picker denied');
  expect(screen.getByText('Composite selected pixels').disabled).toBe(true);
 });
 it('disables new work while another request owns the runtime',()=>{
  render(<ReferenceControls bridge={{}} reference={reference} busy/>);
  expect(screen.getByText('Generate with actual FLUX reference').disabled).toBe(true);
  expect(screen.getByText('Choose background image').disabled).toBe(true);
 });
});
