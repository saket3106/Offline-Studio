// ARGS: { text, click, waitFor, timeoutMs } — type a request in the real composer, wait for an
// assistant action card, optionally click one of its buttons by name, and report the card state.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const ta = document.querySelector('.composer-shell textarea');
if (!ta) return { error: 'composer not found' };
const cardsBefore = document.querySelectorAll('.assistant-card').length;
const messagesBefore = document.querySelectorAll('.message-row').length;
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, ARGS.text); ta.dispatchEvent(new Event('input', { bubbles: true })); await sleep(150);
const t0 = performance.now();
ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
const read = () => { const cards = [...document.querySelectorAll('.assistant-card')]; const c = cards[cards.length - 1];
  return c ? { cls: c.className, label: c.getAttribute('aria-label'), summary: c.querySelector('.assistant-summary')?.innerText,
    buttons: [...c.querySelectorAll('button')].map((b) => b.innerText.trim() || b.getAttribute('aria-label')),
    subject: c.querySelector('input:not([type])')?.value, body: (c.querySelector('textarea')?.value || '').slice(0, 300),
    to: c.querySelector('input[type=email]')?.value } : null; };
let card = null, cardMs = null;
for (let i = 0; i < 100; i++) { await sleep(50); if (document.querySelectorAll('.assistant-card').length > cardsBefore) { cardMs = Math.round(performance.now() - t0); card = read(); break; } }
if (!card) { await sleep(800); return { card: null, chatMessagesAdded: document.querySelectorAll('.message-row').length - messagesBefore, composer: ta.value }; }
if (ARGS.waitFor) { const end = performance.now() + (ARGS.timeoutMs || 90000); while (performance.now() < end && !read().cls.includes(ARGS.waitFor)) await sleep(200); }
let after = null;
if (ARGS.click) {
  const c = [...document.querySelectorAll('.assistant-card')].pop();
  const b = [...c.querySelectorAll('button')].find((x) => x.innerText.trim() === ARGS.click || x.getAttribute('aria-label') === ARGS.click);
  const tc = performance.now(); b?.click();
  for (let i = 0; i < 60; i++) { await sleep(100); const r = read(); if (r && !/is-awaiting|is-running/.test(r.cls)) { after = { ...r, ms: Math.round(performance.now() - tc) }; break; } }
}
return { cardMs, onArrival: card, card: read(), clicked: ARGS.click || null, after, chatMessagesAdded: document.querySelectorAll('.message-row').length - messagesBefore };
