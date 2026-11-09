// Plays the assistant's spoken answers inside the web engine. Audio rendered by the page
// is the reference for Chromium's echo canceller, so the Live Voice microphone hears the
// user, not the assistant, and barge-in can work. The backend (voice_runtime.HybridPlayer)
// sends {op: play|pause|resume|stop|rate, seq, data(base64 wav), rate} and receives
// started / position / ended / error reports; it falls back to Qt playback on error/timeout.

const FRAME_S = 0.02;
/** 20 ms RMS frames of channel 0 (the playback reference for barge-in). */
export function levelFrames(buffer) {
  try {
    const data = buffer.getChannelData(0); const size = Math.max(1, Math.round(buffer.sampleRate * FRAME_S));
    const out = new Float32Array(Math.ceil(data.length / size));
    for (let i = 0, k = 0; i < data.length; i += size, k++) { let s = 0; const e = Math.min(data.length, i + size); for (let j = i; j < e; j++) s += data[j] * data[j]; out[k] = Math.sqrt(s / (e - i)); }
    return out;
  } catch { return new Float32Array(0); }
}

export function createSpeechOutput(report, AudioContextClass = globalThis.AudioContext || globalThis.webkitAudioContext) {
  let ctx = null, current = null, latest = 0, stoppedUpTo = 0, positionTimer = null, activeAt = -1e9, fallbackAt = -1e9;
  const clock = () => (globalThis.performance?.now?.() ?? Date.now());
  // QA counters (read through DevTools) proving which route played the speech.
  const stats = { plays: 0, started: 0, ended: 0, errors: 0, stops: 0, lastError: "" };
  try { globalThis.__offlineSpeechOutput = stats; } catch { /* diagnostics only */ }
  const rawReport = report;
  report = (seq, kind, value) => { if (kind in stats) stats[kind]++; else if (kind === "error") stats.errors++; rawReport(seq, kind, value); };

  const ensure = async () => {
    if (!ctx || ctx.state === "closed") ctx = new AudioContextClass({ latencyHint: "interactive" });
    if (ctx.state === "suspended") {
      // A blocked context never resolves resume(); fail fast so the backend falls back to Qt.
      await Promise.race([ctx.resume(), new Promise((resolve) => setTimeout(resolve, 800))]);
    }
    return ctx;
  };
  const halt = () => {
    clearInterval(positionTimer); positionTimer = null;
    const playing = current; current = null;
    if (playing) { playing.done = true; try { playing.src.onended = null; playing.src.stop(); } catch { /* not started */ } }
  };
  const decode = (base64) => { const raw = atob(base64); const bytes = new Uint8Array(raw.length); for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i); return bytes.buffer; };

  async function play({ seq, data, rate = 1 }) {
    latest = seq; halt(); stats.plays++;
    try {
      const c = await ensure();
      if (c.state !== "running") throw new Error(`audio output is ${c.state}`);
      const buffer = await c.decodeAudioData(decode(data));
      const frames = levelFrames(buffer);
      if (latest !== seq || stoppedUpTo >= seq) return; // superseded or stopped while decoding
      const src = c.createBufferSource(); src.buffer = buffer; src.playbackRate.value = rate || 1; src.connect(c.destination);
      const entry = { seq, src, startedAt: c.currentTime, done: false, rate: rate || 1, frames };
      current = entry;
      src.onended = () => { activeAt = clock(); if (current === entry && !entry.done) { entry.done = true; current = null; clearInterval(positionTimer); report(seq, "ended", 0); } };
      src.start(); activeAt = clock();
      report(seq, "started", 0);
      positionTimer = setInterval(() => {
        if (current === entry && c.state === "running") report(seq, "position", Math.round((c.currentTime - entry.startedAt) * 1000 * entry.rate));
      }, 250);
    } catch (error) {
      stats.lastError = String(error?.message || error).slice(0, 200);
      fallbackAt = clock();
      if (latest === seq) report(seq, "error", 0);
    }
  }

  return {
    handle(message) {
      const { op, seq } = message || {};
      if (op === "play") return play(message);
      if (op === "stop") { stats.stops++; stoppedUpTo = Math.max(stoppedUpTo, seq || 0); if (!current || current.seq <= seq) halt(); return; }
      if (op === "pause") { ctx?.suspend?.(); return; }
      if (op === "resume") { ctx?.resume?.(); return; }
      if (op === "rate" && current) { current.src.playbackRate.value = message.rate || 1; current.rate = message.rate || 1; }
    },
    get playing() { return !!current; },
    /** Barge-in reference: RMS the page is playing now (max over the last 120 ms, covering the speaker->mic
     *  delay), 0 in the gaps of a page-played answer, null when the page is not the speech route (Qt). */
    level() {
      const now = clock();
      if (now - fallbackAt < 30000) return null;
      if (!current) return now - activeAt < 4000 ? 0 : null;
      if (!ctx || ctx.state !== "running") return 0;
      const t = (ctx.currentTime - current.startedAt) * current.rate; const f = current.frames;
      const end = Math.min(f.length - 1, Math.floor((t + 0.02) / FRAME_S)); let peak = 0;
      for (let i = Math.max(0, Math.floor((t - 0.12) / FRAME_S)); i <= end; i++) peak = Math.max(peak, f[i]);
      return peak;
    },
    close() { halt(); ctx?.close?.(); ctx = null; },
  };
}
