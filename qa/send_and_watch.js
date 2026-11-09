// Runs inside the real Offline Studio page (via qa/cdp.mjs evalfile).
// ARGS: { text, timeoutMs }
// Sends one message like a user and watches the newest assistant answer stream.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const text = ARGS.text; const timeout = ARGS.timeoutMs || 300000;
const ta = document.querySelector('.composer-shell textarea');
if (!ta) return { error: 'composer not found' };
const before = document.querySelectorAll('.assistant-message').length;
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, text); ta.dispatchEvent(new Event('input', { bubbles: true }));
await sleep(150);
const sent = performance.now();
ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
let firstText = null, maxLen = 0, wipes = 0, lastLen = 0, samples = 0, sawStreaming = false;
const busy = () => !!document.querySelector('.send-button.stop-button');
while (performance.now() - sent < timeout) {
  await sleep(100); samples++;
  const msgs = document.querySelectorAll('.assistant-message');
  const last = msgs.length > before ? msgs[msgs.length - 1] : null;
  const md = last?.querySelector('.assistant-markdown');
  const len = (md?.innerText || '').trim().length;
  if (md?.classList.contains('streaming-active')) sawStreaming = true;
  if (len > 0 && firstText === null) firstText = Math.round(performance.now() - sent);
  if (len < maxLen * 0.6 && maxLen > 200) wipes++;  // text fell far below its peak: a wipe/restart (final sentence trims are small)
  lastLen = len; maxLen = Math.max(maxLen, len);
  if (!busy() && last && !md?.classList.contains('streaming-active') && performance.now() - sent > 1500) break;
}
await sleep(600);
const msgs = document.querySelectorAll('.assistant-message');
const last = msgs[msgs.length - 1];
const answer = (last?.querySelector('.assistant-markdown')?.innerText || last?.innerText || '').trim();
const words = (answer.match(/\b[\w'’-]+\b/g) || []).length;
return {
  sentAt: new Date().toISOString(), firstTextMs: firstText, totalMs: Math.round(performance.now() - sent), wipes, sawStreaming,
  words, endsWithSentence: /[.!?…)"”]$/.test(answer), continueShown: !!last?.querySelector('.response-footnote .text-action'),
  footnote: last?.querySelector('.response-footnote')?.innerText || null, researchLine: last?.querySelector('.research-line summary')?.innerText || null,
  citationLinks: [...(last?.querySelectorAll('.assistant-markdown a') || [])].map((a) => [a.textContent, a.getAttribute('href')]).slice(0, 12),
  rawIdsLeft: (answer.match(/\bK[0-9a-f]{16}\b/g) || []).length, preview: answer.slice(0, 160), tail: answer.slice(-120),
};
