// Counts barge-in level updates per second from an AudioWorklet vs a 20 ms timer, and reports
// whether the page is hidden (timers are throttled in hidden pages; audio-thread messages are not).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: false } });
const ctx = new AudioContext(); await ctx.resume();
const code = `class P extends AudioWorkletProcessor{constructor(){super();this.n=0;this.block=Math.round(sampleRate*0.02)}process(i){const c=i[0]&&i[0][0];if(c){this.n+=c.length;if(this.n>=this.block){this.port.postMessage(1);this.n=0}}return true}}registerProcessor("rate-probe",P);`;
const url = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
await ctx.audioWorklet.addModule(url);
const node = new AudioWorkletNode(ctx, 'rate-probe'); const g = ctx.createGain(); g.gain.value = 0;
let worklet = 0, timer = 0; node.port.onmessage = () => worklet++;
ctx.createMediaStreamSource(stream).connect(node); node.connect(g); g.connect(ctx.destination);
const id = setInterval(() => timer++, 20);
const t0 = Date.now(); while (Date.now() - t0 < 2000) await new Promise((r) => node.port.addEventListener('message', r, { once: true }));
clearInterval(id); stream.getTracks().forEach((t) => t.stop()); ctx.close();
return { hidden: document.hidden, seconds: 2, workletUpdates: worklet, timerTicks: timer };
