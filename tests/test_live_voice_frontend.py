"""Execute actual frontend handlers against independent microphone/draft invariants."""
import json, re, shutil, subprocess, unittest
from pathlib import Path
S=Path(__file__).resolve().parents[1]
NODE=shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')

class FrontendVoiceTests(unittest.TestCase):
    def run_node(self,code):
        result=subprocess.run([NODE,'-e',code],capture_output=True,text=True,timeout=15)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_only_acknowledged_enable_opens_microphone_and_reentry_is_coalesced(self):
        source=(S/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
        handler=re.search(r'  const toggleLiveVoiceMode = async \(\) => \{.*?\n  \};',source,re.S).group()
        code=r'''
const assert=require('assert/strict');
const handler=HANDLER;
function make(reply,{enabled=false,busy=false}={}){
 const events=[],ref={current:{enabled}},transition={current:false};let requests=0;
 const setAgentMode=v=>events.push(['agent',v]);
 const deps={voiceModeTransition:transition,voiceOptions:ref,applyLiveSession:v=>events.push(['session',v]),setVoiceError:v=>events.push(['error',v]),setVoiceMode:v=>events.push(['mode',v]),setVoicePartial:v=>events.push(['partial',v]),window:{clearTimeout:()=>{}},vadResumeTimer:{current:0},stopVoiceCapture:()=>events.push(['stop']),setVoiceState:v=>events.push(['state',v]),setLiveVoiceState:v=>events.push(['live',v]),parse:(s,f)=>{try{return JSON.parse(s)}catch{return f}},settingsRequest:async()=>{requests++;return typeof reply==='function'?reply():JSON.stringify(reply)},bridge:{setLiveVoiceMode:v=>events.push(['rollback',v])},busy,voiceState:'idle',voiceCaptureRef:{current:null},startVoiceCapture:()=>events.push(['capture'])};
 deps.setAgentMode=setAgentMode;
 // Barge-in monitor and the warm Live Voice microphone are released whenever voice turns off.
 deps.stopBargeIn=()=>events.push(['bargeInStopped']);deps.stopWarmMic=()=>events.push(['micReleased']);
 // Existing handler materializes a client draft before requesting Live Voice.
 deps.materializeChat=async()=>{};
 const fn=new Function(...Object.keys(deps),handler+';return toggleLiveVoiceMode;')(...Object.values(deps));
 return {fn,events,ref,transition,requests:()=>requests};
}
(async()=>{
 for(const reply of [{ok:false,error:'Missing speech assets'},{ok:true,active:false},null]){
  const x=make(reply);await x.fn();assert(!x.events.some(e=>e[0]==='capture'));assert.equal(x.ref.current.enabled,false);assert.equal(x.transition.current,false);assert(x.events.some(e=>e[0]==='error'&&e[1]));
 }
 const failed=make(()=>{throw Error('Disconnected')});await failed.fn();assert(!failed.events.some(e=>e[0]==='capture'));assert(failed.events.some(e=>e[0]==='rollback'&&e[1]===false));
 const good=make({ok:true,active:true,session:{state:'starting',captureRequested:false}});await good.fn();assert.equal(good.events.filter(e=>e[0]==='capture').length,0);assert.equal(good.events.filter(e=>e[0]==='session').length,1);assert.equal(good.ref.current.enabled,true);
 const busy=make({ok:true,active:true},{busy:true});await busy.fn();assert(!busy.events.some(e=>e[0]==='capture'));
 let release;const pending=make(()=>new Promise(r=>release=r));const first=pending.fn();await pending.fn();assert.equal(pending.requests(),1);assert(!pending.events.some(e=>e[0]==='capture'));release(JSON.stringify({ok:true,active:true,session:{state:'starting'}}));await first;assert.equal(pending.events.filter(e=>e[0]==='session').length,1);assert.equal(pending.events.filter(e=>e[0]==='capture').length,0);
 const exit=make({ok:true,active:false},{enabled:true});await exit.fn();assert.equal(exit.ref.current.enabled,false);assert(exit.events.some(e=>e[0]==='stop'));assert(!exit.events.some(e=>e[0]==='capture'));
 console.log('8 activation scenarios passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''.replace('HANDLER',json.dumps(handler))
        self.run_node(code)

    def test_live_transcript_never_overwrites_typed_draft_but_dictation_still_inserts(self):
        source=(S/'frontend-source/src/main.jsx').read_text(encoding='utf-8')
        start=source.index('    if (!voiceEvent || voiceEvent.id === seenVoiceEvent.current) return;')
        end=source.index('  }, [voiceEvent, onVoiceInserted, voiceMode]);',start)
        body=source[start:end]
        self.assertRegex(source,r'const composerProps = \{[^\n]*voiceMode, liveVoiceState,')
        self.assertNotIn('Reset composer state when voice submission',source)
        code=r'''
const assert=require('assert/strict');const body=BODY;
for(const mode of [true,false]){
 let draft='Unfinished typed draft',consumed=0;const deps={voiceEvent:{id:1,text:'Recognized speech',alternatives:[]},seenVoiceEvent:{current:0},voiceMode:mode,onVoiceInserted:()=>consumed++,setText:fn=>draft=fn(draft),voiceRange:{current:null},setTranscriptOptions:()=>{},requestAnimationFrame:()=>{},input:{current:null},bridge:{}};
 new Function(...Object.keys(deps),body)(...Object.values(deps));assert.equal(consumed,1);assert.equal(draft,mode?'Unfinished typed draft':'Unfinished typed draft Recognized speech');
}
console.log('Live Voice draft preservation and ordinary dictation passed');
'''.replace('BODY',json.dumps(body))
        self.run_node(code)

if __name__=='__main__':unittest.main()
