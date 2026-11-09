// ARGS: { seconds } — passive recorder while a human uses the app: voice bar states, assistant
// card states, barge-in detections. Clicks nothing.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const t0 = performance.now(); const ms = () => Math.round(performance.now() - t0);
const voice = []; const cards = {}; let lastVoice = null;
const end = performance.now() + (ARGS.seconds || 300) * 1000;
while (performance.now() < end) {
  await sleep(200);
  const state = document.querySelector('.voice-bar')?.getAttribute('data-state') || 'no-bar';
  if (state !== lastVoice) { voice.push([ms(), state]); lastVoice = state; }
  for (const c of document.querySelectorAll('.assistant-card')) {
    const key = c.getAttribute('aria-label')?.split(':')[0] + '#' + [...document.querySelectorAll('.assistant-card')].indexOf(c);
    const st = c.className.replace('assistant-card ', '');
    const entry = (cards[key] ||= []);
    if (entry[entry.length - 1]?.[1] !== st) entry.push([ms(), st, c.querySelector('.assistant-summary')?.innerText?.slice(0, 120)]);
  }
}
const runs = [...document.querySelectorAll('.assistant-run')].map((r) => ({ cls: r.className, req: r.querySelector('.assistant-run-request')?.innerText, title: r.querySelector('.assistant-run-head')?.title, steps: [...r.querySelectorAll('.assistant-step')].map((s) => s.className.replace('assistant-step ', '') + ' | ' + s.innerText.replace(/\s+/g, ' ').slice(0, 140)) }));
const messages = [...document.querySelectorAll('.message-row')].slice(-12).map((m) => (m.classList.contains('user-message') ? 'U: ' : 'A: ') + (m.querySelector('.assistant-markdown, .user-bubble')?.innerText || '').trim().slice(0, 120));
return { voice, cards, runs, messages, bargeIn: (window.__offlineBargeInDebug || []).map((d) => ({ engine: d.engine, fired: d.fired, peak: d.peak, threshold: d.threshold })), lastBargeIn: window.__offlineBargeIn || null, speech: globalThis.__offlineSpeechOutput || null };
