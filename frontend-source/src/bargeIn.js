// Barge-in: while the assistant speaks, a lightweight level monitor (no transcription)
// listens for the user talking over playback and triggers the existing interrupt.
// TTS plays through Qt (outside Chromium), so the browser's echo canceller does not
// remove speaker leakage: the detector learns and tracks the leakage level itself.

const percentile = (values, p) => { const s = [...values].sort((a, b) => a - b); return s.length ? s[Math.min(s.length - 1, Math.floor(p * s.length))] : 0; };

// Speaker-to-microphone coupling learned during this app session (mic level / playback level), so
// each new spoken answer starts calibrated instead of relearning it. Conservative until learned.
let learnedCoupling = null;
export const resetLearnedCoupling = () => { learnedCoupling = null; };

/** Pure decision logic, unit-tested. Feed RMS samples (0..1) with timestamps in ms.
 *  With `ref` (the level the page is playing right now, 0..1) the threshold follows the assistant's
 *  own loudness: k·ref·ratio while it speaks, and only the room-noise floor in the gaps between
 *  words and sentences. Without it (Qt playback), the older leakage envelope is used.
 *  Measured 2026-11-08: the reference-free rule needed ≥0.035 RMS and ≥2.2× leakage, while the
 *  capture VAD counts speech from 0.012-0.024; QA had boosted the interrupting voice 3× to pass. */
export class BargeInDetector {
  constructor({ floor = 0.035, ratio = 2.2, sustainMs = 250, calibrateMs = 500, maxEcho = 0.2, halfLifeMs = 3000,
    refFloor = 0.012, refRatio = 1.4, initialCoupling = 1.5, maxCoupling = 4 } = {}) {
    Object.assign(this, { floor, ratio, sustainMs, calibrateMs, maxEcho, halfLifeMs, refFloor, refRatio, initialCoupling, maxCoupling });
    this.reset();
  }
  reset() { this.started = null; this.last = null; this.samples = []; this.echo = 0; this.speechMs = 0; this.fired = false;
    this.ref = null; this.noise = 0.004; this.coupling = learnedCoupling ?? this.initialCoupling; this.couplingSamples = []; }
  get threshold() {
    if (this.ref === null) return Math.max(this.floor, Math.min(this.maxEcho, this.echo) * this.ratio);
    return Math.max(this.refFloor, this.noise * 3.5, this.coupling * this.ref * this.refRatio + this.noise * 2);
  }
  /** Returns true exactly once, when sustained speech above the speaker-leakage level is detected. */
  push(rms, now, ref = null) {
    if (this.fired) return false;
    if (this.started === null) this.started = now;
    const dt = this.last === null ? 0 : Math.max(0, now - this.last); this.last = now;
    this.ref = Number.isFinite(ref) ? Math.max(0, ref) : null;
    if (this.ref !== null) return this.pushWithReference(rms, now, dt);
    if (now - this.started < this.calibrateMs) { this.samples.push(rms); this.echo = percentile(this.samples, 0.9); return false; }
    // Leakage envelope: decays slowly, follows playback that stays below the threshold.
    this.echo *= Math.pow(0.5, dt / this.halfLifeMs);
    // Speech dips between syllables, so "continuously above" never held in real tests
    // (peaks 0.68 vs threshold 0.04 without firing). Accumulate loud time instead: loud
    // frames add, quiet frames take it back at half speed; isolated clicks cannot add up.
    const step = Math.min(dt, 60);
    if (rms > this.threshold) {
      this.speechMs += step;
      if (this.speechMs >= this.sustainMs) { this.fired = true; return true; }
    } else {
      this.speechMs = Math.max(0, this.speechMs - step * 0.5);
      if (this.speechMs === 0) this.echo = Math.max(this.echo, rms);
    }
    return false;
  }
  pushWithReference(rms, now, dt) {
    const ref = this.ref; const playing = ref > 0.03; const echoPart = Math.max(0, rms - this.noise);
    if (now - this.started < this.calibrateMs) {
      // Learn the coupling from the first half second of playback (the user rarely speaks this early).
      if (playing) { this.couplingSamples.push(echoPart / ref); this.coupling = Math.min(this.maxCoupling, Math.max(learnedCoupling ?? 0, percentile(this.couplingSamples, 0.9))); }
      else if (ref < 0.005) this.noise = Math.min(0.02, Math.max(0.001, this.noise * 0.9 + rms * 0.1));
      return false;
    }
    const step = Math.min(dt, 60); const threshold = this.threshold; const expected = this.coupling * ref + this.noise;
    if (rms > threshold) {
      this.speechMs += step;
      if (this.speechMs >= this.sustainMs) { this.fired = true; return true; }
      return false;
    }
    // Overlapped speech is partly masked by playback: frames that are above the expected leakage
    // but below the threshold drain slowly; frames that look like plain leakage drain at half speed.
    const ambiguous = playing && rms > expected * 1.2;
    this.speechMs = Math.max(0, this.speechMs - step * (ambiguous ? 0.15 : 0.5));
    if (this.speechMs === 0 && !ambiguous) {
      if (playing) {
        // Leakage envelope on the coupling: only frames consistent with leakage update it, so the
        // user's quiet speech cannot ratchet it up; relaxes slowly.
        this.coupling = Math.min(this.maxCoupling, Math.max(this.coupling * Math.pow(0.5, dt / (this.halfLifeMs * 3)), echoPart / ref));
        learnedCoupling = Math.max(0.05, this.coupling);
      } else if (ref < 0.005) this.noise = Math.min(0.02, Math.max(0.001, this.noise * 0.97 + rms * 0.03));
    }
    return false;
  }

}

/** Linear resampling of 16-bit PCM (the capture context may run at another rate than the monitor). */
export function resampleInt16(pcm, from, to) {
  if (!from || !to || from === to || !pcm.length) return Int16Array.from(pcm);
  const length = Math.max(1, Math.round(pcm.length * to / from)); const out = new Int16Array(length); const step = from / to;
  for (let i = 0; i < length; i++) { const x = i * step, j = Math.floor(x), f = x - j; const a = pcm[Math.min(j, pcm.length - 1)], b = pcm[Math.min(j + 1, pcm.length - 1)]; out[i] = Math.round(a + (b - a) * f); }
  return out;
}

/** Barge-in audio carry: the monitor records a rolling 2 s pre-roll (detection can lag speech onset by ~1 s) while the answer plays.
 *  When the user interrupts, it freezes (keeps everything from just before their first word)
 *  and keeps recording until the next turn's capture starts, so those words reach transcription. */
export class PcmCarry {
  constructor({ preMs = 2000, maxMs = 12000 } = {}) { Object.assign(this, { preMs, maxMs }); this.chunks = []; this.ms = 0; this.rate = 0; this.frozen = false; this.taken = false; }
  push(pcm, rate) {
    if (this.taken || !pcm?.length || !rate) return;
    if (rate !== this.rate) { if (this.frozen && this.rate) return; this.chunks = []; this.ms = 0; this.rate = rate; }
    if (this.frozen && this.ms >= this.maxMs) return;
    this.chunks.push(pcm); this.ms += 1000 * pcm.length / rate;
    if (!this.frozen) while (this.ms > this.preMs && this.chunks.length > 1) { const c = this.chunks.shift(); this.ms -= 1000 * c.length / rate; }
  }
  freeze() { this.frozen = true; }
  /** Returns the carried audio once, as ~100 ms Int16Array chunks at targetRate ([] unless frozen). */
  take(targetRate) {
    if (!this.frozen || this.taken) return [];
    this.taken = true;
    const total = this.chunks.reduce((n, c) => n + c.length, 0); const all = new Int16Array(total); let o = 0;
    for (const c of this.chunks) { all.set(c, o); o += c.length; }
    this.chunks = [];
    const pcm = resampleInt16(all, this.rate, targetRate || this.rate); const size = Math.max(800, Math.round((targetRate || this.rate) * 0.1)); const out = [];
    for (let i = 0; i < pcm.length; i += size) out.push(pcm.slice(i, i + size));
    return out;
  }
}

/** Monitors a microphone stream (shared or its own); returns stop(). Calls onBargeIn({detectedAt, threshold, echo}).
 *  With a PcmCarry, also records audio (worklet engine only) and freezes it when barge-in fires. */
/** `reference()` returns the level the page is playing now (0..1), or null when speech is not played by the page. */
export async function startBargeInMonitor({ stream = null, deviceId = "", onBargeIn, detector = new BargeInDetector(), carry = null, reference = null } = {}) {
  let owned = null;
  if (!stream) {
    const audio = { echoCancellation: true, noiseSuppression: true, autoGainControl: false, channelCount: { ideal: 1 } };
    if (deviceId) audio.deviceId = { exact: deviceId };
    stream = owned = await navigator.mediaDevices.getUserMedia({ audio, video: false });
  }
  const Context = window.AudioContext || window.webkitAudioContext;
  // 16 kHz matches the capture context, so carried audio usually needs no resampling.
  let context; try { context = new Context({ sampleRate: 16000, latencyHint: "interactive" }); } catch { context = new Context({ latencyHint: "interactive" }); }
  const source = context.createMediaStreamSource(stream);
  let stopped = false, timer = null, node = null, sink = null, workletUrl = null;
  if (context.state === "suspended") context.resume().catch(() => {});
  // QA diagnostics (read through DevTools): levels the detector saw during playback.
  const debug = { startedAt: performance.now(), samples: 0, peak: 0, threshold: 0, echo: 0, contextState: context.state, fired: false, engine: "" };
  try { (window.__offlineBargeInDebug ||= []).push(debug); if (window.__offlineBargeInDebug.length > 20) window.__offlineBargeInDebug.shift(); } catch { /* diagnostics only */ }
  const onLevel = (rms) => {
    if (stopped) return;
    const now = performance.now(); let ref = null; try { ref = reference ? reference() : null; } catch { ref = null; }
    const fired = detector.push(rms, now, ref);
    debug.samples++; debug.peak = Math.max(debug.peak, +rms.toFixed(4)); debug.threshold = +detector.threshold.toFixed(4); debug.echo = +detector.echo.toFixed(4); debug.contextState = context.state;
    debug.ref = ref === null ? null : +ref.toFixed(4); debug.coupling = +detector.coupling.toFixed(3); debug.noise = +detector.noise.toFixed(4); if (ref !== null) debug.refFrames = (debug.refFrames || 0) + 1;
    if (fired) { debug.fired = true; carry?.freeze(); onBargeIn?.({ detectedAt: now, threshold: detector.threshold, echo: detector.echo }); }
  };
  // Levels are measured on the audio thread: page timers are throttled to ~1/s while the
  // window is hidden (e.g. the user is in a game), audio-thread messages are not.
  try {
    if (!context.audioWorklet) throw new Error("no audio worklet");
    // Each 20 ms block posts its level and its 16-bit PCM (kept only by the carry).
    const code = `class BargeInLevel extends AudioWorkletProcessor{constructor(){super();this.sum=0;this.n=0;this.block=Math.round(sampleRate*0.02);this.pcm=new Int16Array(this.block)}
      process(inputs){const ch=inputs[0]&&inputs[0][0];if(ch){for(let i=0;i<ch.length;i++){const v=Math.max(-1,Math.min(1,ch[i]));this.pcm[this.n]=v<0?Math.round(v*32768):Math.round(v*32767);this.sum+=v*v;if(++this.n>=this.block){const pcm=this.pcm;this.port.postMessage({rms:Math.sqrt(this.sum/this.n),pcm:pcm.buffer},[pcm.buffer]);this.pcm=new Int16Array(this.block);this.sum=0;this.n=0}}}return true}}
      registerProcessor("barge-in-level",BargeInLevel);`;
    workletUrl = URL.createObjectURL(new Blob([code], { type: "text/javascript" }));
    await context.audioWorklet.addModule(workletUrl);
    node = new AudioWorkletNode(context, "barge-in-level", { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1, channelCountMode: "explicit" });
    sink = context.createGain(); sink.gain.value = 0; // keep the graph pulled without making sound
    node.port.onmessage = (event) => { const d = event.data; if (typeof d === "number") { onLevel(d); return; } if (!stopped && d?.pcm) carry?.push(new Int16Array(d.pcm), context.sampleRate); onLevel(d.rms); };
    debug.rate = context.sampleRate;
    source.connect(node); node.connect(sink); sink.connect(context.destination);
    debug.engine = "worklet";
  } catch {
    const analyser = context.createAnalyser(); analyser.fftSize = 1024; source.connect(analyser);
    const buffer = new Float32Array(analyser.fftSize);
    timer = setInterval(() => {
      analyser.getFloatTimeDomainData(buffer);
      let sum = 0; for (let i = 0; i < buffer.length; i++) sum += buffer[i] * buffer[i];
      onLevel(Math.sqrt(sum / buffer.length));
    }, 20);
    debug.engine = "timer";
  }
  return () => {
    if (stopped) return; stopped = true; clearInterval(timer);
    try { if (node) { node.port.onmessage = null; node.disconnect(); } sink?.disconnect(); source.disconnect(); } catch { /* already disconnected */ }
    if (workletUrl) URL.revokeObjectURL(workletUrl);
    owned?.getTracks().forEach((t) => t.stop()); context.close().catch(() => {});
  };
}

/** Live-voice display: keep "speaking" while the backend briefly reports "thinking"
 *  between streamed sentences of the same answer, so the bar does not flicker. */
export function smoothLiveState(previousShown, next, spokeThisTurn) {
  if (next === "thinking" && spokeThisTurn) return "speaking";
  return next;
}
