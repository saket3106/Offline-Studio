import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,cleanup,fireEvent} from '@testing-library/react';
import {VoiceBar,VoiceInputMeter,voicePresentation} from './VoiceSession.jsx';
describe('voice readiness and measured input',()=>{
 it('never says ready or listening before audio frames',()=>{
  expect(voicePresentation({state:'starting'}).title).toContain('Preparing');
  expect(voicePresentation({state:'listening',captureReady:false}).title).toContain('Starting');
  expect(voicePresentation({state:'listening',captureReady:true}).title).toBe('Listening');
 });
 it('uses plain state labels and never mentions a permission wait',()=>{
  for(const state of ['starting','listening','transcribing','thinking','speaking','paused','error']){
   const view=voicePresentation({state,prepared:true,captureReady:true});
   expect(view.title+' '+view.detail).not.toMatch(/permission|audio frames/i);
  }
  expect(voicePresentation({state:'thinking'}).title).toBe('Thinking…');
  expect(voicePresentation({state:'speaking'}).title).toBe('Speaking — talk to interrupt');
 });
 it('responds to measured PCM, resets on mute and disconnects cleanly',()=>{
  const view=render(<VoiceInputMeter active/>);window.dispatchEvent(new CustomEvent('offline-voice-level',{detail:.08}));
  expect(screen.getByRole('meter').value).toBeCloseTo(.4);
  view.rerender(<VoiceInputMeter active={false}/>);expect(screen.getByRole('meter').value).toBe(0);
  window.dispatchEvent(new CustomEvent('offline-voice-level',{detail:.1}));expect(screen.getByRole('meter').value).toBe(0);cleanup();
 });
});
describe('composer voice bar',()=>{
 it('renders state from the session, interrupts only while answering and ends on Escape',()=>{
  const control=vi.fn();
  const view=render(<VoiceBar session={{state:'listening',captureReady:true}} transcript="what is machine" onControl={control}/>);
  expect(screen.getByRole('status').textContent).toBe('Listening');
  expect(screen.getByText('what is machine')).toBeTruthy();
  expect(screen.getByRole('button',{name:'Stop speaking'}).disabled).toBe(true);
  view.rerender(<VoiceBar session={{state:'speaking',captureReady:true}} onControl={control}/>);
  fireEvent.click(screen.getByRole('button',{name:'Stop speaking'}));expect(control).toHaveBeenLastCalledWith('interrupt');
  fireEvent.click(screen.getByRole('button',{name:'Mute microphone'}));expect(control).toHaveBeenLastCalledWith('mute');
  fireEvent.keyDown(window,{key:'Escape'});expect(control).toHaveBeenLastCalledWith('exit');
  expect(document.querySelector('.voice-orb')).toBeNull();cleanup();
 });
});
