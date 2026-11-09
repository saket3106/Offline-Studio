import React from 'react';
import {describe,it,expect} from 'vitest';
import {render,screen,cleanup,fireEvent,act} from '@testing-library/react';
import {ArtifactPane,openArtifact,canPreview,previewDocument} from './ArtifactPane.jsx';

describe('code artifact pane',()=>{
 it('previews only markup it can render safely',()=>{
  expect(canPreview('html')).toBe(true);
  expect(canPreview('SVG')).toBe(true);
  expect(canPreview('xml','<svg viewBox="0 0 1 1"/>')).toBe(true);
  expect(canPreview('xml','<note/>')).toBe(false);
  expect(canPreview('python')).toBe(false);
 });
 it('injects a no-network CSP into every preview document',()=>{
  for(const doc of [previewDocument('html','<p>x</p>'),previewDocument('html','<html><head><title>t</title></head><body></body></html>'),previewDocument('svg','<svg/>')]){
   expect(doc).toContain("default-src 'none'");
   expect(doc).not.toMatch(/connect-src/);
  }
  expect(previewDocument('html','<html><head><title>t</title></head></html>').indexOf('Content-Security-Policy')).toBeLessThan(previewDocument('html','<html><head><title>t</title></head></html>').indexOf('<title>'));
 });
 it('opens sandboxed, switches preview / code / split, and closes on Escape',()=>{
  render(<ArtifactPane/>);
  expect(screen.queryByLabelText('Code preview')).toBeNull();
  act(()=>openArtifact({lang:'html',source:'<b>hi</b>'}));
  const frame=document.querySelector('iframe');
  expect(frame.getAttribute('sandbox')).toBe('allow-scripts');
  fireEvent.click(screen.getByRole('radio',{name:/Split/}));
  expect(document.querySelector('iframe')).not.toBeNull();expect(document.querySelector('.artifact-code')).not.toBeNull();
  fireEvent.click(screen.getByRole('radio',{name:/Code/}));
  expect(document.querySelector('iframe')).toBeNull();
  fireEvent.keyDown(screen.getByLabelText('Code preview'),{key:'Escape'});
  expect(screen.queryByLabelText('Code preview')).toBeNull();
  cleanup();
 });
 it('shows non-markup as code only and hides when the inspector takes the column',()=>{
  render(<ArtifactPane/>);
  act(()=>openArtifact({lang:'python',source:'print(1)'}));
  expect(screen.getAllByRole('radio').map(b=>b.dataset.view)).toEqual(['code']);
  expect(document.querySelector('iframe')).toBeNull();
  act(()=>window.dispatchEvent(new Event('studio:artifact-close')));
  expect(screen.queryByLabelText('Code preview')).toBeNull();
  cleanup();
 });
});
