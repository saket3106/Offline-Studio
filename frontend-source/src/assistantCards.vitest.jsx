import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {AssistantCards,mergeAssistantCard} from './assistantCards.jsx';
afterEach(cleanup);

const launch={id:'a',kind:'launch',status:'awaiting',source:'voice',request:"I'm feeling like playing GTA 5",summary:'Launch Grand Theft Auto V and switch to High performance with Game Mode on.',gaming:true,
 app:{name:'Grand Theft Auto V',source:'steam',target:'steam://rungameid/271590'},alternatives:[{name:'Grand Theft Auto IV',source:'steam',target:'steam://rungameid/12210'}],power:{target:{name:'High performance'}}};
const handlers=()=>({onExecute:vi.fn(),onCancel:vi.fn(),onDismiss:vi.fn(),onSaveEmail:vi.fn(async()=>({ok:true}))});

describe('assistant action cards',()=>{
 it('nothing runs until Play is pressed; choice and gaming toggle are passed',()=>{
  const h=handlers();render(<AssistantCards cards={[launch]} {...h}/>);
  expect(h.onExecute).not.toHaveBeenCalled();
  expect(screen.getByText('or say “yes”')).toBeTruthy();
  fireEvent.click(screen.getByLabelText(/Grand Theft Auto IV/));
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button',{name:'Play'}));
  expect(h.onExecute).toHaveBeenCalledWith('a',{appIndex:1,power:false});
 });
 it('without an account the draft opens in Gmail; account setup is optional',()=>{
  const h=handlers();
  render(<AssistantCards cards={[{id:'e',kind:'email',status:'awaiting',subject:'Leave request',body:'Hi',to:'boss@example.com',configured:false,summary:'Email'}]} {...h}/>);
  expect(screen.getByRole('group',{name:'Email account setup',hidden:true})).toBeTruthy();
  expect(screen.queryByRole('button',{name:'Send'})).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Open in Gmail'}));
  expect(h.onExecute).toHaveBeenCalledWith('e',{to:'boss@example.com',subject:'Leave request',body:'Hi',sendAt:null,via:'gmail'});
 });
 it('WhatsApp card opens WhatsApp only after the button, with edited text',()=>{
  const h=handlers();
  render(<AssistantCards cards={[{id:'w',kind:'whatsapp',status:'awaiting',to:'Mom',phone:'',text:'I will be late',summary:'WhatsApp to Mom'}]} {...h}/>);
  expect(h.onExecute).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Message'),{target:{value:'Running late, home by 8'}});
  fireEvent.click(screen.getByRole('button',{name:'Open in WhatsApp'}));
  expect(h.onExecute).toHaveBeenCalledWith('w',{to:'Mom',phone:'',text:'Running late, home by 8',sendAt:null});
 });
 it('configured email sends edited fields',()=>{
  const h=handlers();
  render(<AssistantCards cards={[{id:'e',kind:'email',status:'awaiting',subject:'S',body:'B',to:'sam@example.com',configured:true,summary:'Email'}]} {...h}/>);
  fireEvent.change(screen.getByLabelText('Subject'),{target:{value:'New subject'}});
  fireEvent.click(screen.getByRole('button',{name:'Send'}));
  expect(h.onExecute).toHaveBeenCalledWith('e',{to:'sam@example.com',subject:'New subject',body:'B',sendAt:null});
 });
 it('Cancel and close cancel a pending card; events merge by id',()=>{
  const h=handlers();render(<AssistantCards cards={[launch]} {...h}/>);
  fireEvent.click(screen.getByRole('button',{name:'Cancel'}));expect(h.onCancel).toHaveBeenCalledWith('a');
  const merged=mergeAssistantCard([launch],{id:'a',status:'done',summary:'Launching'});
  expect(merged).toHaveLength(1);expect(merged[0].status).toBe('done');expect(merged[0].app.name).toBe('Grand Theft Auto V');
 });
});
