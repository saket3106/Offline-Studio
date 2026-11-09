import test from 'node:test';
import assert from 'node:assert/strict';
import { createSpeechOutput } from './speechOutput.js';

class FakeSource { constructor() { this.playbackRate = { value: 1 }; this.started = false; this.stopped = false; } connect() {} start() { this.started = true; } stop() { this.stopped = true; } }
class FakeContext {
  static last = null;
  constructor() { this.state = 'running'; this.currentTime = 0; this.destination = {}; this.sources = []; FakeContext.last = this; }
  async resume() { this.state = 'running'; } async suspend() { this.state = 'suspended'; } async close() { this.state = 'closed'; }
  async decodeAudioData() { return { duration: 1 }; }
  createBufferSource() { const s = new FakeSource(); this.sources.push(s); return s; }
}
const wav = Buffer.from('RIFF').toString('base64');
globalThis.atob ??= (b) => Buffer.from(b, 'base64').toString('binary');

test('plays a chunk, reports started then ended', async () => {
  const reports = []; const out = createSpeechOutput((...a) => reports.push(a), FakeContext);
  await out.handle({ op: 'play', seq: 1, data: wav, rate: 1 });
  assert.deepEqual(reports[0], [1, 'started', 0]); assert.ok(FakeContext.last.sources[0].started);
  FakeContext.last.sources[0].onended();
  assert.deepEqual(reports.at(-1), [1, 'ended', 0]); out.close();
});

test('stop halts playback immediately and never reports ended', async () => {
  const reports = []; const out = createSpeechOutput((...a) => reports.push(a), FakeContext);
  await out.handle({ op: 'play', seq: 2, data: wav });
  const src = FakeContext.last.sources[0];
  out.handle({ op: 'stop', seq: 2 });
  assert.ok(src.stopped); assert.equal(out.playing, false);
  assert.equal(reports.filter((r) => r[1] === 'ended').length, 0); out.close();
});

test('a chunk stopped while decoding never starts', async () => {
  const reports = []; const out = createSpeechOutput((...a) => reports.push(a), FakeContext);
  const pending = out.handle({ op: 'play', seq: 3, data: wav });
  out.handle({ op: 'stop', seq: 3 }); await pending;
  assert.equal(reports.length, 0); out.close();
});

test('blocked audio output reports error so the backend falls back to Qt', async () => {
  class Blocked extends FakeContext { constructor() { super(); this.state = 'suspended'; } async resume() {} }
  const reports = []; const out = createSpeechOutput((...a) => reports.push(a), Blocked);
  await out.handle({ op: 'play', seq: 4, data: wav });
  assert.deepEqual(reports, [[4, 'error', 0]]); out.close();
});
