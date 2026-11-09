// Usage: node qa/vmic_barge_in.mjs <dir-with-ask.wav-and-int.wav> <out.json>   (app running with QTWEBENGINE_REMOTE_DEBUGGING=127.0.0.1:9333)
// Make the WAVs silently (16 kHz mono) with System.Speech SpeechSynthesizer.SetOutputToWaveFile; nothing is played aloud.
// Expect: barge.carryMs > 0 and the second user message contains the interruption's first word.
// Internal barge-in check: a virtual microphone (WAV files played into a MediaStream) replaces
// getUserMedia, and spoken answers are routed to a silent node, so nothing is audible.
import { readFileSync, writeFileSync } from "node:fs";
// Optional: [intGain] level of the interrupting voice (0.33 ≈ normal speaking level 0.03 RMS; old runs used 3),
// [echoGain] fraction of the spoken answer leaked back into the virtual mic (speaker echo, no canceller).
const dir = process.argv[2]; const out = process.argv[3]; const intGain = Number(process.argv[4] || 3); const echoGain = Number(process.argv[5] || 0);
const b64 = (name) => readFileSync(`${dir}/${name}.wav`).toString("base64");
const targets = await (await fetch("http://127.0.0.1:9333/json/list")).json();
const page = targets.find((t) => t.type === "page" && /index\.html/.test(t.url)) || targets.find((t) => t.type === "page");
const ws = new WebSocket(page.webSocketDebuggerUrl); let id = 0; const waiting = new Map();
ws.onmessage = (e) => { const m = JSON.parse(e.data); if (m.id && waiting.has(m.id)) { waiting.get(m.id)(m); waiting.delete(m.id); } };
await new Promise((r) => (ws.onopen = r));
const ev = (expression) => new Promise((resolve) => { const n = ++id; waiting.set(n, (m) => resolve(m.result?.exceptionDetails ? { error: JSON.stringify(m.result.exceptionDetails).slice(0, 400) } : m.result?.result?.value)); ws.send(JSON.stringify({ id: n, method: "Runtime.evaluate", params: { expression, awaitPromise: true, returnByValue: true } })); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const state = () => ev(`document.querySelector('.voice-bar')?.getAttribute('data-state') || 'no-bar'`);

const setup = await ev(`(async () => {
  if (!window.__vmic) {
    const ctx = new AudioContext({ sampleRate: 16000 }); const dest = ctx.createMediaStreamDestination();
    const hum = ctx.createConstantSource(); hum.offset.value = 0; hum.connect(dest); hum.start();
    window.__vmic = { ctx, dest, marks: [] };
    window.__vmic.say = async (name, b64, gain = 1) => { const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0)); const buf = await ctx.decodeAudioData(bytes.buffer); const src = ctx.createBufferSource(); src.buffer = buf; const g = ctx.createGain(); g.gain.value = gain; src.connect(g); g.connect(dest); await ctx.resume(); src.start(); window.__vmic.marks.push([name, Math.round(performance.now()), Math.round(buf.duration * 1000)]); return Math.round(buf.duration * 1000); };
    navigator.mediaDevices.getUserMedia = async () => dest.stream.clone();
    // Mute spoken answers (QA only): buffer sources connected to a speaker output go to a silent gain.
    const connect = AudioNode.prototype.connect; const echoes = new Map(); window.__vmic.echoGain = 0;
    const echoInput = (c) => { if (!echoes.has(c)) { const tap = c.createMediaStreamDestination(); const back = ctx.createMediaStreamSource(tap.stream); const delay = ctx.createDelay(1); delay.delayTime.value = 0.04; const g = ctx.createGain(); g.gain.value = 1; connect.call(back, delay); connect.call(delay, g); connect.call(g, dest); const level = c.createGain(); connect.call(level, tap); echoes.set(c, level); } const level = echoes.get(c); level.gain.value = window.__vmic.echoGain; return level; };
    AudioNode.prototype.connect = function (target, ...rest) {
      if (target instanceof AudioDestinationNode && this instanceof AudioBufferSourceNode && target.context !== ctx) { const g = this.context.createGain(); g.gain.value = 0; connect.call(g, target); connect.call(this, echoInput(this.context)); return connect.call(this, g, ...rest); }
      return connect.call(this, target, ...rest);
    };
  }
  window.__vmic.echoGain = ${echoGain}; window.__vmic.marks = []; window.__e2eStates = []; let last = null; clearInterval(window.__e2eTimer);
  window.__e2eTimer = setInterval(() => { const st = document.querySelector('.voice-bar')?.getAttribute('data-state') || 'no-bar'; if (st !== last) { window.__e2eStates.push([st, Math.round(performance.now())]); last = st; } }, 25);
  document.querySelector('.new-chat-button')?.click(); await new Promise((r) => setTimeout(r, 1500));
  window.__offlineBargeIn = null; document.querySelector('button[aria-label="Start Live Voice"]')?.click(); return 'ok';
})()`);
console.log("setup", setup, "intGain", intGain, "echoGain", echoGain);
for (let i = 0; i < 300 && (await state()) !== "listening"; i++) await sleep(100);
await sleep(500);
await ev(`window.__vmic.say('ask', ${JSON.stringify(b64("ask"))})`);
let s; for (let i = 0; i < 900 && (s = await state()) !== "speaking"; i++) await sleep(100);
await sleep(2500);
const intMs = await ev(`window.__vmic.say('int', ${JSON.stringify(b64("int"))}, ${intGain})`);
await sleep(intMs + 1500);
for (let i = 0; i < 300; i++) { s = await state(); if (s === "thinking" || s === "speaking") break; await sleep(100); }
await sleep(1500 + Number(process.argv[6] || 0)); // [holdMs] keep watching (false-trigger check with intGain 0)
const result = await ev(`({ marks: window.__vmic.marks, states: window.__e2eStates, barge: window.__offlineBargeIn, debug: (window.__offlineBargeInDebug||[]).slice(-1),
  messages: [...document.querySelectorAll('.message-row')].map(m=>({ role: m.classList.contains('user-message')?'user':'assistant', text:(m.querySelector('.user-bubble,.message-content')?.textContent||m.textContent||'').split(/[\\s]+/).join(' ').trim().slice(0,120) })) })`);
await ev(`(async()=>{window.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}));await new Promise(r=>setTimeout(r,1200));clearInterval(window.__e2eTimer);return !document.querySelector('.voice-bar')})()`);
writeFileSync(out, JSON.stringify(result, null, 2));
const base = result.marks?.find((m) => m[0] === "int")?.[1] || 0;
console.log("int speech starts @0 lasts", result.marks?.find((m) => m[0] === "int")?.[2], "ms");
console.log("states", (result.states || []).filter((x) => x[1] >= base - 3000).map((x) => `${x[0]}@${x[1] - base}`).join(" "));
console.log("barge", result.barge && { fire: Math.round(result.barge.detectedAt - base), carryMs: result.barge.carryMs, stopMs: result.barge.stopMs });
console.log(result.messages.map((m) => `${m.role}: ${m.text}`).join("\n"));
ws.close();
