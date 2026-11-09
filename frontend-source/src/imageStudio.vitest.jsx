import React from 'react';
import {describe,it,expect,vi,afterEach} from 'vitest';
import {render,screen,cleanup,fireEvent} from '@testing-library/react';
import {ImageStudio,studioProgress,BeforeAfter} from './product.jsx';

afterEach(()=>{cleanup();try{localStorage.clear();}catch{}});

describe('Image Studio controls',()=>{
 it('reads diffusion steps from the engine status',()=>{
  expect(studioProgress('Generating image · step 7 of 28')).toEqual({step:7,total:28,label:'Generating image'});
  expect(studioProgress('Upscaling · step 2 of 4')).toEqual({step:2,total:4,label:'Upscaling'});
  expect(studioProgress('Loading local image model…')).toBeNull();
  expect(studioProgress('step 9 of 4')).toBeNull();
 });
 it('shows Step X/28 with a progress bar while generating',()=>{
  render(<ImageStudio onPrompt={()=>{}} busy status="Generating image · step 7 of 28"/>);
  expect(screen.getByText('Step 7/28')).toBeTruthy();
  const bar=screen.getByRole('progressbar');
  expect(bar.getAttribute('aria-valuenow')).toBe('7');expect(bar.getAttribute('aria-valuemax')).toBe('28');
 });
 it('sends a locked seed and the negative prompt with Generate',()=>{
  const onPrompt=vi.fn();
  render(<ImageStudio onPrompt={onPrompt}/>);
  fireEvent.change(screen.getByLabelText('Studio image description'),{target:{value:'a lighthouse at dusk'}});
  fireEvent.click(screen.getByRole('button',{name:/^Random$/}));
  const seed=screen.getByLabelText('Seed');
  fireEvent.change(seed,{target:{value:'42x'}});expect(seed.value).toBe('42');
  fireEvent.change(screen.getByLabelText('Negative prompt'),{target:{value:'text, watermark'}});
  fireEvent.click(screen.getByRole('button',{name:/Generate/}));
  expect(onPrompt).toHaveBeenCalledWith('Create a 1024x576 image of a lighthouse at dusk',null,{seed:42,negative:'text, watermark'});
 });
 it('sends no seed when unlocked',()=>{
  const onPrompt=vi.fn();
  render(<ImageStudio onPrompt={onPrompt}/>);
  fireEvent.change(screen.getByLabelText('Studio image description'),{target:{value:'a cat'}});
  fireEvent.click(screen.getByRole('button',{name:/Generate/}));
  expect(onPrompt.mock.calls[0][2]).toEqual({seed:null,negative:''});
 });
 it('offers before/after only for an image with a known source, and the slider is keyboard operable',()=>{
  const images=[{id:'b',path:'C:/i/b.png',parentId:'a',operation:'enhance_image',displayName:'B'},{id:'a',path:'C:/i/a.png',displayName:'A'}];
  render(<ImageStudio onPrompt={()=>{}} images={images}/>);
  fireEvent.click(screen.getByRole('button',{name:'B'}));
  fireEvent.click(screen.getByRole('button',{name:'Before / after'}));
  const slider=screen.getByLabelText('Before and after comparison');
  fireEvent.change(slider,{target:{value:'80'}});expect(slider.getAttribute('aria-valuetext')).toBe('80% after');
  fireEvent.click(screen.getByRole('button',{name:'A'}));
  expect(screen.queryByRole('button',{name:'Before / after'})).toBeNull();
  cleanup();
  render(<BeforeAfter before="a.png" after="b.png"/>);
  const range=screen.getByLabelText('Before and after comparison');
  expect(range.value).toBe('50');
  fireEvent.change(range,{target:{value:'20'}});
  expect(document.querySelector('.before-after-top').style.clipPath).toBe('inset(0 80% 0 0)');
 });
});
