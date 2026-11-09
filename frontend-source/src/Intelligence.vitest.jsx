import React from 'react';
import {describe,it,expect,vi} from 'vitest';
import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {IntelligenceBar,ResearchPanel,KnowledgeWorkspace} from './Intelligence.jsx';
import {afterEach} from 'vitest';
afterEach(cleanup);
function bridge(){
 const listeners=new Set();const state={settings:{intelligence_mode:'offline',research_provider:'none',research_permission:'ask'},providerConfigured:false,providerHealth:'NOT_CONFIGURED',semantic:'NOT_CONFIGURED_LEXICAL_ACTIVE'};
 const b={event:{connect:f=>listeners.add(f),disconnect:f=>listeners.delete(f)},getIntelligenceState:cb=>cb(JSON.stringify({ok:true,value:state})),setIntelligenceSettings:vi.fn((raw,cb)=>{Object.assign(state.settings,JSON.parse(raw));cb(JSON.stringify({ok:true,value:state}))}),openIntelligenceSource:vi.fn((run,id,cb)=>cb('{"ok":true}'))};
 b.workspaceRequest=(action,raw,cb)=>{const a=JSON.parse(raw),id=Math.random().toString();cb(JSON.stringify({ok:true,requestId:id}));queueMicrotask(()=>{const value=action==='projectsList'?{projects:[]}:a.operation==='list'?{documents:[],chunks:0}:a.operation==='runs'?{runs:[]}:a.operation==='memories'?{memories:[]}:{};listeners.forEach(f=>f(JSON.stringify({type:'workspaceResult',requestId:id,ok:true,value})))})};return b;
}
describe('Intelligence integration',()=>{
 it('changes mode only through acknowledged native persistence',async()=>{const b=bridge();render(<IntelligenceBar bridge={b} busy={false} chatId="a"/>);const web=await screen.findByRole('button',{name:'Web'});fireEvent.click(web);await waitFor(()=>expect(web.getAttribute('aria-pressed')).toBe('true'));expect(JSON.parse(b.setIntelligenceSettings.mock.calls[0][0]).intelligence_mode).toBe('web');});
 it('keeps controls disabled while a request owns the runtime',async()=>{render(<IntelligenceBar bridge={bridge()} busy chatId="a"/>);expect((await screen.findByRole('button',{name:'Web'})).disabled).toBe(true)});
 it('shows explicit provider setup without pretending discovery is configured',async()=>{render(<KnowledgeWorkspace bridge={bridge()} busy={false}/>);fireEvent.click(screen.getByRole('button',{name:'Provider setup'}));await screen.findByText('Search provider');expect(screen.getByText(/Web search needs no key/)).toBeTruthy();expect(screen.getByText(/NOT_CONFIGURED/)).toBeTruthy();});
 it('opens only recorded source identifiers through the native bridge',()=>{const b=bridge();render(<ResearchPanel bridge={b} packet={{id:'run-real',state:'PARTIAL',counts:{fetched:1,cited:0},sources:[{id:'K0123456789abcdef',title:'Recorded source',fetchStatus:'FETCHED',excerpt:'Actual evidence fixture'}]}}/>);fireEvent.click(screen.getByRole('button',{name:'Recorded source'}));expect(b.openIntelligenceSource.mock.calls[0].slice(0,2)).toEqual(['run-real','K0123456789abcdef']);expect(screen.getByText(/Evidence fetched/)).toBeTruthy()});
});
