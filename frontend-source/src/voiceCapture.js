// Lightweight endpointing over real PCM duration. No semantic/acoustic barge-in claim.
export const END_SILENCE_MS = 700;
export class SpeechEndpoint {
  constructor() { this.noise = .002; this.onset = 0; this.voiced = 0; this.lastVoice = null; this.speech = false; }
  push(pcm, rate, now) {
    let energy = 0, clipped = 0;
    for (const v of pcm) { const x = v / 32768; energy += x*x; if (Math.abs(x) > .98) clipped++; }
    const rms = Math.sqrt(energy / Math.max(1, pcm.length));
    const duration = 1000 * pcm.length / Math.max(8000, rate);
    const threshold = Math.max(.012, Math.min(.04, this.noise * 3));
    const voiced = rms > (this.speech ? threshold * .72 : threshold);
    if (voiced) {
      this.onset += duration;
      if (this.speech) { this.voiced += duration; this.lastVoice = now; }
      else if (this.onset >= 180) { this.speech = true; this.voiced = this.onset; this.lastVoice = now; }
    } else {
      if (!this.speech) this.onset = 0;
      this.noise = Math.max(.001, Math.min(.008, this.noise*.98 + rms*.02));
    }
    return { rms, voiced, clipped: clipped / Math.max(1, pcm.length), speech: this.speech,
      discard: this.speech && this.voiced < 300 && this.lastVoice !== null && now-this.lastVoice >= 1500,
      // 700 ms of silence ends the turn (was 1000 ms): snappier replies, still tolerant of short pauses.
      finish: this.speech && this.voiced >= 300 && this.lastVoice !== null && now-this.lastVoice >= END_SILENCE_MS };
  }
}

export function acceptsSession(snapshot, current) {
  if (!snapshot || typeof snapshot.generation !== 'number') return false;
  if (!current?.sessionId) return true;
  return snapshot.generation > current.generation ||
    snapshot.sessionId === current.sessionId && snapshot.generation === current.generation &&
      (snapshot.revision || 0) >= (current.revision || 0);
}

export function voiceDeadline(promise, milliseconds, message, disposeLate) {
  let expired=false,timer;
  const deadline=new Promise((_,reject)=>{timer=setTimeout(()=>{expired=true;reject(new Error(message));},milliseconds);});
  const operation=Promise.resolve(promise).then(value=>{if(expired)disposeLate?.(value);return value;});
  return Promise.race([operation,deadline]).finally(()=>clearTimeout(timer));
}
