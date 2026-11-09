import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,fireEvent,cleanup} from '@testing-library/react';
import {ChatRenameInput,ChatBulkBar} from './sidebarControls.jsx';
afterEach(cleanup);

describe('inline chat rename',()=>{
 it('Enter saves a trimmed name',()=>{
  const save=vi.fn(),cancel=vi.fn();render(<ChatRenameInput initial="Old title" onSave={save} onCancel={cancel}/>);
  const box=screen.getByRole('textbox',{name:'Chat name'});
  fireEvent.change(box,{target:{value:'  Trip planning  '}});fireEvent.keyDown(box,{key:'Enter'});
  expect(save).toHaveBeenCalledWith('Trip planning');expect(cancel).not.toHaveBeenCalled();
 });
 it('Esc cancels without saving',()=>{
  const save=vi.fn(),cancel=vi.fn();render(<ChatRenameInput initial="Old" onSave={save} onCancel={cancel}/>);
  const box=screen.getByRole('textbox',{name:'Chat name'});fireEvent.change(box,{target:{value:'New'}});fireEvent.keyDown(box,{key:'Escape'});
  expect(cancel).toHaveBeenCalledTimes(1);expect(save).not.toHaveBeenCalled();
 });
 it('rejects an empty name and keeps editing',()=>{
  const save=vi.fn(),cancel=vi.fn();render(<ChatRenameInput initial="Old" onSave={save} onCancel={cancel}/>);
  const box=screen.getByRole('textbox',{name:'Chat name'});fireEvent.change(box,{target:{value:'   '}});fireEvent.keyDown(box,{key:'Enter'});
  expect(save).not.toHaveBeenCalled();expect(cancel).not.toHaveBeenCalled();
  expect(box.getAttribute('aria-invalid')).toBe('true');expect(screen.getByRole('alert').textContent).toMatch(/empty/i);
  fireEvent.change(box,{target:{value:'Fixed'}});expect(box.getAttribute('aria-invalid')).toBeNull();
 });
 it('blur with an empty name cancels instead of saving',()=>{
  const save=vi.fn(),cancel=vi.fn();render(<ChatRenameInput initial="Old" onSave={save} onCancel={cancel}/>);
  const box=screen.getByRole('textbox',{name:'Chat name'});fireEvent.change(box,{target:{value:''}});fireEvent.blur(box);
  expect(save).not.toHaveBeenCalled();expect(cancel).toHaveBeenCalled();
 });
});

describe('bulk selection bar',()=>{
 const props=over=>({count:0,total:3,onSelectAll:vi.fn(),onClear:vi.fn(),onDelete:vi.fn(),onExport:vi.fn(),onCancel:vi.fn(),...over});
 it('exposes a named toolbar with a live count and accessible controls',()=>{
  const p=props({count:2});render(<ChatBulkBar {...p}/>);
  expect(screen.getByRole('toolbar',{name:'Selected conversations'})).toBeTruthy();
  expect(screen.getByRole('status').textContent).toBe('2 selected');
  for(const name of ['Select all conversations','Export selected conversations','Delete 2 selected conversations','Cancel selection'])expect(screen.getByRole('button',{name})).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Delete 2 selected conversations'}));expect(p.onDelete).toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Select all conversations'}));expect(p.onSelectAll).toHaveBeenCalled();
 });
 it('disables delete with nothing selected and toggles to Clear when all are selected',()=>{
  const view=render(<ChatBulkBar {...props()}/>);
  expect(screen.getByRole('button',{name:'Delete 0 selected conversations'}).disabled).toBe(true);
  const p=props({count:3});view.rerender(<ChatBulkBar {...p}/>);
  fireEvent.click(screen.getByRole('button',{name:'Clear selection'}));expect(p.onClear).toHaveBeenCalled();
 });
 it('is keyboard operable: arrows move focus, Escape cancels',()=>{
  const p=props({count:1});render(<ChatBulkBar {...p}/>);
  const toolbar=screen.getByRole('toolbar');const first=screen.getByRole('button',{name:'Select all conversations'});
  first.focus();fireEvent.keyDown(toolbar,{key:'ArrowRight'});expect(document.activeElement).toBe(screen.getByRole('button',{name:'Export selected conversations'}));
  fireEvent.keyDown(toolbar,{key:'Escape'});expect(p.onCancel).toHaveBeenCalled();
 });
});
