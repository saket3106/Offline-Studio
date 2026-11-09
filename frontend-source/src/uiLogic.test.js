import {test} from 'node:test';
import assert from 'node:assert/strict';
import {formatModelName,friendlyState,virtualRows,collapseDraftChats,shouldShowSources,usedMemorySources,commandActionKey,resolveTheme,commandMatches} from './uiLogic.js';
import {createDesktopAdapter,desktopCall} from './dataAccess.js';
test('model names preserve quantization separately and never infer capability',()=>{
 assert.deepEqual(formatModelName('Openai_Gpt Oss 20b'),{name:'GPT-OSS 20B',quantization:''});
 assert.equal(formatModelName('Qwen3-4B-Q4_K_M.gguf').quantization,'Q4_K_M');
 assert.equal(friendlyState('present'),'Installed');assert.equal(friendlyState('custom'),'custom');
});
test('5000 images remain bounded and every last item is reachable',()=>{
 const top=virtualRows({count:5000,width:1000,height:600,scrollTop:0});assert(top.end<=24);assert.equal(top.start,0);
 const end=virtualRows({count:5000,width:1000,height:600,scrollTop:top.height-600});assert.equal(end.end,5000);assert(end.end-end.start<40);
 const narrow=virtualRows({count:2,width:100,height:400,scrollTop:0});assert.equal(narrow.columns,1);assert.equal(narrow.end,2);
 assert.equal(virtualRows({count:0,width:100,height:400,scrollTop:0}).height,0);
});
test('virtual lists clamp stale scroll positions after content shrinks',()=>{
 const list=virtualRows({count:5,width:800,height:500,scrollTop:50000,minWidth:100000,rowHeight:38,overscan:4});
 assert.equal(list.start,0);
 assert.equal(list.end,5);
 assert(list.start<=list.end);
 const gallery=virtualRows({count:5,width:1000,height:600,scrollTop:100000,rowHeight:248});
 assert.equal(gallery.start,0);
 assert.equal(gallery.end,5);
 const intermediate=virtualRows({count:400,width:800,height:500,scrollTop:1e9,minWidth:100000,rowHeight:38,overscan:4});
 assert(intermediate.start<intermediate.end);
 assert(intermediate.end<=400);
});
test('history collapses repeated unpinned new-chat drafts without deleting records',()=>{
 const chats=[
  {id:'a',title:'Project notes',updated:5},
  {id:'draft-1',title:'New chat',updated:4},
  {id:'draft-2',title:'New chat',updated:3},
  {id:'draft-3',title:'New chat',updated:2},
  {id:'pinned',title:'New chat',updated:1,pinned:true}
 ];
 const collapsed=collapseDraftChats(chats);
 assert.equal(collapsed.length,3);
 assert.equal(collapsed[1].isDraftGroup,true);
 assert.equal(collapsed[1].draftCount,3);
 assert.deepEqual(collapsed[1].draftIds,['draft-1','draft-2','draft-3']);
 assert.equal(chats.length,5);
 const withCurrent=collapseDraftChats(chats,'draft-2');
 assert.equal(withCurrent.find(c=>c.id==='draft-2')?.title,'New chat');
 assert.equal(withCurrent.find(c=>c.isDraftGroup)?.draftCount,2);
});
test('source chip requires usage evidence instead of retrieval alone',()=>{
 assert(!shouldShowSources({content:'Hello',metrics:{memory_sources:[{id:'S1'}]}}));
 assert(shouldShowSources({content:'Supported [S1]',metrics:{memory_sources:[{id:'S1'}]}}));
 assert(shouldShowSources({metrics:{memory_sources:[{id:'S2',used:true}]}}));
});
test('theme resolution follows system only for Auto',()=>{
 assert.equal(resolveTheme('auto',true),'light');assert.equal(resolveTheme('auto',false),'dark');assert.equal(resolveTheme('contrast',true),'dark');
 assert.equal(resolveTheme('dark',true),'dark');assert(commandMatches({label:'Settings Compute memory'},'memory settings'));assert(!commandMatches({label:'Models'},'voice'));
});
test('native adapter preserves binding, callback values and signal identity',async()=>{
 const signal={connect(){}};const native={value:42,event:signal,get(cb){cb(this.value);},throws(){throw Error('native failure');}};
 const adapter=createDesktopAdapter(native);assert.equal(adapter,createDesktopAdapter(native));assert.equal(adapter.event,signal);assert.equal(adapter.missing,undefined);
 assert.equal(await desktopCall(adapter,'get'),42);assert.equal(await desktopCall(adapter,'missing'),null);await assert.rejects(desktopCall(adapter,'throws'),/native failure/);
});

test('source list exposes only independently used or actually cited memory evidence',()=>{
 const msg={content:'Result based on [S2]',metrics:{memory_sources:[
  {id:'S1',title:'retrieved but unused'}, {id:'S2',title:'cited'},
  {id:'S3',title:'explicitly used',used:true}
 ]}};
 assert.deepEqual(usedMemorySources(msg).map(s=>s.id),['S2','S3']);
 assert.equal(shouldShowSources(msg),true);
 assert.deepEqual(usedMemorySources({content:'Nothing cited',metrics:msg.metrics}).map(s=>s.id),['S3']);
 assert.deepEqual(usedMemorySources({content:'No sources',metrics:{memory_sources:[]}}),[]);
 assert.deepEqual(usedMemorySources({content:'[S1]',metrics:{memory_sources:[{id:'S1',used:false}]}}).map(s=>s.id),['S1']);
});
test('same-named conversations retain distinct command identities',()=>{
 const a={id:'chat-101',label:'Open chat: Notes'};
 const b={id:'chat-102',label:'Open chat: Notes'};
 assert.notEqual(commandActionKey(a),commandActionKey(b));
 assert.equal(commandActionKey({label:'Settings'}),'Settings');
});

test('research citation IDs render as numbered source links, unresolved IDs are removed', async () => {
  const { linkCitations } = await import('./uiLogic.js');
  const sources = [{ id: 'K5379ff5a635b7b44', url: 'https://example.org/survey' }, { id: 'K4760e53a0e72714d', url: 'https://en.wikipedia.org/wiki/Grok_(chatbot%29' }];
  assert.equal(linkCitations('and efficiency K5379ff5a635b7b44.', sources), 'and efficiency [\\[1\\]](https://example.org/survey).');
  assert.equal(linkCitations('a "Think" mode [K4760e53a0e72714d](https://en.wikipedia.org/wiki/Grok_(chatbot%29).', sources), 'a "Think" mode [\\[2\\]](https://en.wikipedia.org/wiki/Grok_%28chatbot%29).');
  assert.equal(linkCitations('Unknown Kaaaaaaaaaaaaaaaa here.', sources), 'Unknown here.');
  assert.equal(linkCitations('Plain answer with no ids.', []), 'Plain answer with no ids.');
});
