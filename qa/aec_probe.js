// Double-talk probe. The page plays audio continuously (the "assistant"); an outside process
// plays a different sound from ~7.6 s (the "user"). With echo cancellation ON, the user's sound
// must remain while the page's own sound is removed.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const open = (ec) => navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: ec, noiseSuppression: ec, autoGainControl: false } });
const ctx = new AudioContext(); await ctx.resume();
const meters = [];
for (const ec of [true, false]) {
  const stream = await open(ec); const an = ctx.createAnalyser(); an.fftSize = 1024; ctx.createMediaStreamSource(stream).connect(an);
  meters.push({ ec, stream, an, buf: new Float32Array(1024) });
}
const t0 = performance.now();
const measure = async (ms) => {
  const s = meters.map(() => []); const end = performance.now() + ms;
  while (performance.now() < end) {
    meters.forEach((m, i) => { m.an.getFloatTimeDomainData(m.buf); let q = 0; for (const v of m.buf) q += v * v; s[i].push(Math.sqrt(q / m.buf.length)); });
    await sleep(20);
  }
  return Object.fromEntries(meters.map((m, i) => { const v = s[i].sort((a, b) => a - b); return [m.ec ? 'aecOn' : 'aecOff', { p50: +v[v.length >> 1].toFixed(4), p90: +v[Math.floor(v.length * 0.9)].toFixed(4) }]; }));
};
const silence = await measure(1500);
const out = new AudioContext(); await out.resume();
const osc = out.createOscillator(); osc.type = 'square'; osc.frequency.value = 330;
const lfo = out.createOscillator(); lfo.frequency.value = 5; const lfoGain = out.createGain(); lfoGain.gain.value = 90; lfo.connect(lfoGain).connect(osc.frequency);
const g = out.createGain(); g.gain.value = 0.2; osc.connect(g).connect(out.destination); osc.start(); lfo.start();
await sleep(1200);
const assistantOnly = await measure(2500);
await sleep(Math.max(0, 7700 - (performance.now() - t0)));
const doubleTalk = await measure(2200);
osc.stop(); lfo.stop(); out.close();
await sleep(300);
const userOnly = await measure(900);
meters.forEach((m) => m.stream.getTracks().forEach((t) => t.stop())); ctx.close();
return { silence, assistantOnly, doubleTalk, userOnly };
