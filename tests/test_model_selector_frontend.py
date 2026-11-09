"""Run the canonical selector's real async handlers; no React/model mocks prove inference."""
import json,re,shutil,subprocess,unittest
from pathlib import Path
S=Path(__file__).resolve().parents[1]
NODE=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')

class SelectorTests(unittest.TestCase):
 def test_acknowledgement_navigation_and_stale_reply_rules(self):
  source=(S/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
  functions=[]
  for name,args in [('handleSelectModel','modelId'),('handleNewChatWithModel','modelId'),('fetchModels','')]:
   functions.append(re.search(r'  const '+name+r' = async \('+args+r'\) => \{.*?\n  \};',source,re.S).group())
  script=r'''
const assert=require('assert/strict');const handlers=HANDLERS;
function make(reply,{busy=false,chat='chat-a'}={}){
 const state={selected:'old',errors:[],opened:[],closed:false,calls:0,models:[]};const ref={current:chat};
 const deps={busy,switching:false,currentChat:chat,bridge:{setChatModel(){},newChatWithModel(){},listLocalModels(){},getChatModel(){}},setSwitching(){},setSelectionError:e=>state.errors.push(e),parse:(x,f)=>{try{return JSON.parse(x)}catch{return f}},call:async(b,m,...args)=>{state.calls++;return typeof reply==='function'?reply(m,...args):reply},modelChatRef:ref,setChatModel:v=>state.selected=v,onRefresh(){},onOpenChat:async id=>{state.opened.push(id);return true},setOpen:v=>state.closed=!v,modelRefreshEpoch:{current:0},setAvailableModels:v=>state.models=v};
 const fns=new Function(...Object.keys(deps),handlers.join('\n')+';return {handleSelectModel,handleNewChatWithModel,fetchModels};')(...Object.values(deps));return {state,ref,...fns};
}
(async()=>{
 const rejected=make(JSON.stringify({ok:false,error:'Busy'}));await rejected.handleSelectModel('new');assert.equal(rejected.state.selected,'old');assert(rejected.state.errors.includes('Busy'));
 const accepted=make(JSON.stringify({ok:true}));await accepted.handleSelectModel('new');assert.equal(accepted.state.selected,'new');
 const busy=make(JSON.stringify({ok:true}),{busy:true});await busy.handleSelectModel('new');assert.equal(busy.state.calls,0);
 let release;const delayed=make(()=>new Promise(r=>release=r));const pending=delayed.handleSelectModel('new');delayed.ref.current='chat-b';release(JSON.stringify({ok:true}));await pending;assert.equal(delayed.state.selected,'old');
 const created=make('new-chat');await created.handleNewChatWithModel('new');assert.deepEqual(created.state.opened,['new-chat']);assert(created.state.closed);
 const failed=make('');await failed.handleNewChatWithModel('new');assert.deepEqual(failed.state.opened,[]);assert(!failed.state.closed);assert(failed.state.errors.some(Boolean));
 const stale=make(m=>m==='listLocalModels'?JSON.stringify({ok:true,models:[{id:'old'}]}):'old',{chat:'chat-a'});stale.ref.current='chat-b';await stale.fetchModels();assert.deepEqual(stale.state.models,[]);assert.equal(stale.state.selected,'old');
 console.log('7 selector scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('HANDLERS',json.dumps(functions))
  result=subprocess.run([NODE,'-e',script],capture_output=True,text=True,timeout=12);self.assertEqual(result.returncode,0,result.stderr)
 def test_voice_events_are_bound_even_when_one_chat_id_is_empty(self):
  source=(S/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
  line=next(x.strip() for x in source.splitlines() if 'event.type?.startsWith("voice")' in x)
  code="const accept=new Function('event','currentChatRef',"+json.dumps(line+';return true')+");const a=require('assert/strict');"
  code+="for(const [event,current,expected] of [[{type:'voiceText',chatId:'a'},'b',false],[{type:'voiceText',chatId:'a'},'',false],[{type:'voiceText',chatId:''},'b',false],[{type:'voiceText',chatId:''},'',true],[{type:'voiceText',chatId:'b'},'b',true],[{type:'voiceError'},'b',true]])a.equal(accept(event,{current})!==undefined,expected);"
  result=subprocess.run([NODE,'-e',code],capture_output=True,text=True,timeout=12);self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
