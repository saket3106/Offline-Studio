import test from 'node:test';
import assert from 'node:assert/strict';
import { BargeInDetector, smoothLiveState, PcmCarry, resampleInt16, resetLearnedCoupling } from './bargeIn.js';

// Feed [rms, count] runs every 20 ms; return the time it fired, or null.
const run = (d, samples, step = 20) => { let t = 0; for (const [rms, n] of samples) for (let i = 0; i < n; i++) { if (d.push(rms, t)) return t; t += step; } return null; };

test('steady speaker leakage alone never triggers', () => {
  assert.equal(run(new BargeInDetector(), [[0.03, 25], [0.05, 300]]), null);
});

test('leakage that varies between sentences and pauses never triggers', () => {
  const pattern = []; for (let k = 0; k < 20; k++) pattern.push([0.06, 40], [0.01, 15]);
  assert.equal(run(new BargeInDetector(), [[0.06, 25], ...pattern]), null);
});

test('user speech well above leakage triggers once after the 250 ms sustain window', () => {
  const d = new BargeInDetector();
  const at = run(d, [[0.03, 25], [0.03, 10], [0.25, 40]]);
  const onset = 35 * 20;
  assert.ok(at !== null && at >= onset + 220 && at <= onset + 280, `triggered at ${at}`);
  assert.equal(d.push(0.3, 9000), false); // fires only once
});

test('natural speech with dips between syllables still triggers quickly', () => {
  const syllables = []; for (let k = 0; k < 10; k++) syllables.push([0.3, 4], [0.01, 2]); // 80 ms loud, 40 ms dip
  const at = run(new BargeInDetector(), [[0.02, 25], ...syllables]);
  assert.ok(at !== null && at - 500 <= 450, `triggered at ${at}`);
});

test('short clicks or coughs below the sustain window are ignored', () => {
  assert.equal(run(new BargeInDetector(), [[0.02, 25], [0.3, 5], [0.02, 10], [0.3, 6], [0.02, 50]]), null);
});

test('very loud leakage raises the threshold but it is capped', () => {
  const d = new BargeInDetector();
  run(d, [[0.5, 25]]);
  assert.ok(Math.abs(d.threshold - 0.44) < 1e-9); // min(maxEcho 0.2, echo) * 2.2
});

test('bar keeps showing speaking between streamed sentences, not before speech', () => {
  assert.equal(smoothLiveState('speaking', 'thinking', true), 'speaking');
  assert.equal(smoothLiveState('transcribing', 'thinking', false), 'thinking');
  assert.equal(smoothLiveState('speaking', 'listening', true), 'listening');
});

// Barge-in audio carry: the interrupting words must reach the next turn.
const block = (value, n = 320) => new Int16Array(n).fill(value); // 20 ms at 16 kHz

test('carry keeps only a short pre-roll while the answer plays', () => {
  const c = new PcmCarry({ preMs: 100 });
  for (let i = 0; i < 50; i++) c.push(block(i), 16000);
  assert.ok(c.ms <= 100);
  assert.deepEqual(c.take(16000), [], 'nothing handed over without a barge-in');
});

test('after barge-in the carry keeps pre-roll plus everything until taken, once, in order', () => {
  const c = new PcmCarry({ preMs: 100, maxMs: 8000 });
  for (let i = 0; i < 50; i++) c.push(block(1), 16000);
  c.freeze();
  for (let i = 0; i < 40; i++) c.push(block(2), 16000); // 800 ms of the user's words
  const chunks = c.take(16000);
  const all = chunks.flatMap((x) => [...x]);
  assert.equal(all.length, 5 * 320 + 40 * 320);
  assert.equal(all[0], 1); assert.equal(all.at(-1), 2);
  assert.ok(chunks.every((x) => x.length <= 1600), '100 ms chunks');
  assert.deepEqual(c.take(16000), [], 'handed over only once');
  c.push(block(3), 16000); assert.equal(c.chunks.length, 0, 'no recording after hand-over');
});

test('frozen carry stops at its cap instead of dropping the first words', () => {
  const c = new PcmCarry({ preMs: 20, maxMs: 100 });
  c.push(block(7), 16000); c.freeze();
  for (let i = 0; i < 20; i++) c.push(block(8), 16000);
  const all = c.take(16000).flatMap((x) => [...x]);
  assert.equal(all[0], 7); assert.ok(all.length <= 6 * 320);
});

test('carry resamples to the capture rate', () => {
  const c = new PcmCarry({ preMs: 1000 }); c.push(block(100, 960), 48000); c.freeze();
  const all = c.take(16000).flatMap((x) => [...x]);
  assert.equal(all.length, 320); assert.ok(all.every((v) => v === 100));
  assert.equal(resampleInt16(new Int16Array([0, 100]), 16000, 32000).length, 4);
});

// Playback reference (page speech route): threshold follows the assistant's own loudness.
const runRef = (d, samples, step = 20) => { let t = 0; for (const [rms, ref, n] of samples) for (let i = 0; i < n; i++) { if (d.push(rms, t, ref)) return t; t += step; } return null; };
const answer = (k, frames) => { const out = []; for (let i = 0; i < frames; i++) { const ref = i % 15 < 11 ? 0.12 + 0.08 * Math.sin(i) : 0.0; out.push([k * ref + 0.004, ref, 1]); } return out; };

test('reference: speaker leakage that follows playback never triggers (strong coupling, no echo canceller)', () => {
  resetLearnedCoupling();
  assert.equal(runRef(new BargeInDetector(), answer(1.6, 1500)), null);
  assert.equal(runRef(new BargeInDetector(), answer(0.15, 1500)), null);
});

test('reference: a normal speaking voice (0.03 RMS) is caught in the gaps of a page-played answer', () => {
  resetLearnedCoupling();
  const d = new BargeInDetector();
  const speech = []; for (let i = 0; i < 60; i++) { const ref = i % 15 < 11 ? 0.14 : 0; speech.push([0.15 * ref + 0.03 + (i % 3 ? 0 : -0.01), ref, 1]); }
  const at = runRef(d, [...answer(0.15, 50), ...speech]);
  assert.ok(at !== null && at - 1000 <= 700, `triggered at ${at}`);
});

test('reference: the old rule misses that same quiet voice', () => {
  const d = new BargeInDetector(); const s = []; for (let i = 0; i < 60; i++) s.push([0.03 + (i % 3 ? 0 : -0.01), 1]);
  assert.equal(run(d, [[0.03, 25], ...s]), null);
});

test('reference: coupling learned on one answer carries to the next monitor', () => {
  resetLearnedCoupling();
  runRef(new BargeInDetector(), answer(0.3, 200));
  const next = new BargeInDetector();
  assert.ok(next.coupling >= 0.25 && next.coupling < 1, `coupling ${next.coupling}`);
});

test('reference: room noise in the gaps is not speech', () => {
  resetLearnedCoupling();
  const quiet = []; for (let i = 0; i < 600; i++) quiet.push([0.006 + (i % 7) * 0.001, 0, 1]);
  assert.equal(runRef(new BargeInDetector(), quiet), null);
});

test('reference: jittery leakage (±35 %, random gaps, 3 couplings, 5 answers each) never triggers', () => {
  let seed = 7; const rnd = () => ((seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648);
  for (const k of [0.1, 0.5, 1.4]) {
    resetLearnedCoupling();
    for (let a = 0; a < 5; a++) {
      const frames = []; let ref = 0;
      for (let i = 0; i < 900; i++) { if (rnd() < 0.06) ref = rnd() < 0.3 ? 0 : 0.05 + rnd() * 0.25; frames.push([k * ref * (0.65 + rnd() * 0.7) + 0.003 + rnd() * 0.004, ref, 1]); }
      assert.equal(runRef(new BargeInDetector(), frames), null, `coupling ${k} answer ${a}`);
    }
  }
});
