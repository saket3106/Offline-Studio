// ARGS: { seconds } — new chat, start Live Voice, record bar states, barge-in detection and
// detection→playback-stop latency while a human talks over the spoken answer. End voice at the end.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.querySelector('.new-chat-button')?.click(); await sleep(1800);
const start = document.querySelector('button[aria-label="Start Live Voice"]');
if (!start) return { error: 'Start Live Voice not found' };
window.__offlineBargeIn = null;
const t0 = performance.now(); start.click();
const ms = (t = performance.now()) => Math.round(t - t0);
const timeline = []; const bargeIns = []; let lastState = null, lastBarge = null;
for (let i = 0; i < (ARGS.seconds || 120) * 50; i++) {
  await sleep(20);
  const state = document.querySelector('.voice-bar')?.getAttribute('data-state') || 'no-bar';
  if (state !== lastState) { timeline.push({ ms: ms(), state }); lastState = state; }
  const b = window.__offlineBargeIn;
  if (b && (b !== lastBarge || (b.stopMs !== null && !bargeIns.find((x) => x.detectedAt === ms(b.detectedAt) && x.stopMs !== null)))) {
    const entry = { detectedAt: ms(b.detectedAt), stopMs: b.stopMs, threshold: +b.threshold.toFixed(4), echo: +b.echo.toFixed(4) };
    const existing = bargeIns.find((x) => x.detectedAt === entry.detectedAt);
    if (existing) Object.assign(existing, entry); else bargeIns.push(entry);
    lastBarge = b;
  }
}
const messages = [...document.querySelectorAll('.message-row')].map((m) => ({ role: m.classList.contains('user-message') ? 'user' : 'assistant', text: (m.querySelector('.assistant-markdown, .user-bubble')?.innerText || '').trim().slice(0, 140) }));
window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await sleep(1200);
return { timeline, bargeIns, messages, ended: !document.querySelector('.voice-bar'),
  detector: window.__offlineBargeInDebug || [], speechOutput: globalThis.__offlineSpeechOutput || null };
