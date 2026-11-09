import React,{useEffect,useRef} from 'react';
import {Mic,MicOff,Square,X,RotateCcw} from 'lucide-react';

// Plain-language labels for the single voice state machine
// (idle → listening → transcribing → thinking → speaking → listening, + error).
export function voicePresentation(session={}) {
 const state=session.state;
 const statuses={starting:session.prepared?'Starting microphone…':'Preparing voice…',listening:session.captureReady?'Listening':'Starting microphone…',speech_detected:'Listening',transcribing:'Transcribing…',thinking:'Thinking…',speaking:'Speaking — talk to interrupt',interrupting:'Stopping…',recovering:'Reconnecting…',paused:'Microphone muted',error:session.error||'Voice needs attention'};
 const details={starting:'Loading local speech models',listening:session.captureReady?'Speak naturally · pause to send':'Opening the microphone',speech_detected:'Pause to send',transcribing:'Local Whisper',thinking:'Local model',speaking:'Local Kokoro voice',paused:'Session kept · unmute to continue',error:'Retry, or end and check Settings › Voice'};
 return {title:statuses[state]||'Closing…',detail:details[state]||''};
}

// The meter updates its own DOM from measured PCM; it never rerenders the chat.
export function VoiceInputMeter({active}) {
 const meter=useRef(null);
 useEffect(()=>{
  const update=event=>{if(meter.current)meter.current.value=active?Math.min(1,Math.max(0,event.detail||0)*5):0;};
  window.addEventListener('offline-voice-level',update);
  if(meter.current)meter.current.value=0;
  return()=>window.removeEventListener('offline-voice-level',update);
 },[active]);
 return <meter ref={meter} className="voice-input-meter" min="0" max="1" defaultValue="0" aria-label="Measured microphone level"/>;
}

/** Live Voice lives in the composer itself: one slim bar, never a card over the chat. */
export function VoiceBar({session={state:'idle'},transcript='',onControl}) {
 const state=session.state;
 const busyAnswer=['thinking','speaking'].includes(state);
 const view=voicePresentation(session);
 useEffect(()=>{
  const key=event=>{if(event.key==='Escape'&&!event.defaultPrevented){event.preventDefault();onControl?.('exit');}};
  window.addEventListener('keydown',key);return()=>window.removeEventListener('keydown',key);
 },[onControl]);
 return <section className="voice-bar" aria-label="Live Voice" data-state={state}>
  <VoiceInputMeter active={!!session.captureReady && ['listening','speech_detected'].includes(state)}/>
  <div className="voice-bar-text">
   <span className="voice-bar-state" role="status" aria-live="polite">{view.title}</span>
   {transcript ? <span className="voice-bar-transcript" aria-live="polite">{transcript}</span> : <span className="voice-bar-detail">{view.detail}</span>}
  </div>
  <div className="voice-bar-actions">
   {state==='error' && <button type="button" className="icon-button" onClick={()=>onControl?.('retry')} aria-label="Retry Live Voice" title="Retry"><RotateCcw size={16}/></button>}
   <button type="button" className="icon-button" onClick={()=>onControl?.(session.muted?'unmute':'mute')} aria-pressed={!!session.muted} aria-label={session.muted?'Unmute microphone':'Mute microphone'} title={session.muted?'Unmute':'Mute'}>{session.muted?<MicOff size={16}/>:<Mic size={16}/>}</button>
   <button type="button" className="icon-button" onClick={()=>onControl?.('interrupt')} disabled={!busyAnswer} aria-label="Stop speaking" title="Stop speaking"><Square size={14}/></button>
   <button type="button" className="icon-button voice-bar-end" onClick={()=>onControl?.('exit')} aria-label="End Live Voice" title="End voice (Esc)"><X size={16}/></button>
  </div>
 </section>;
}
