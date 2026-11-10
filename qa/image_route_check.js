// Runs inside the real Offline Studio page (via qa/cdp.mjs evalfile).
// ARGS: { text, attachLatest?: bool, timeoutMs? }
// Sends one message like a user and reports what came back: a new image, an edited image, or text.
// attachLatest clicks the newest image's "Create variation" button first, which leaves that image attached
// in the composer (the owner's "attached by mistake" case), then replaces the prefilled text with ARGS.text.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const timeout = ARGS.timeoutMs || 420000;
const images = () => [...document.querySelectorAll('.assistant-message img')].map((img) => img.getAttribute('src') || '');
if (ARGS.attachLatest) {
  const buttons = document.querySelectorAll('.image-action-btn[title="Create variation"]');
  const button = buttons[buttons.length - 1];
  if (!button) return { error: 'no Create variation button to attach an image' };
  button.click(); await sleep(600);
}
const ta = document.querySelector('.composer-shell textarea');
if (!ta) return { error: 'composer not found' };
const attachedBefore = document.querySelectorAll('.attachment-strip > *').length;
const before = document.querySelectorAll('.assistant-message').length;
const imagesBefore = new Set(images());
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, ARGS.text); ta.dispatchEvent(new Event('input', { bubbles: true }));
await sleep(200);
const sent = performance.now();
ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
const busy = () => !!document.querySelector('.send-button.stop-button');
const statuses = new Set();
while (performance.now() - sent < timeout) {
  await sleep(250);
  const msgs = document.querySelectorAll('.assistant-message');
  const last = msgs.length > before ? msgs[msgs.length - 1] : null;
  const status = last?.querySelector('.message-status, .status-line, [role="status"]')?.innerText;
  if (status) statuses.add(status.slice(0, 80));
  if (!busy() && last && performance.now() - sent > 2000) break;
}
await sleep(800);
const msgs = document.querySelectorAll('.assistant-message');
const last = msgs[msgs.length - 1];
const fresh = images().filter((src) => !imagesBefore.has(src));
return {
  text: ARGS.text.slice(0, 80), attachedBefore, totalMs: Math.round(performance.now() - sent),
  newImages: fresh.length, statuses: [...statuses].slice(0, 6),
  reply: (last?.querySelector('.assistant-markdown')?.innerText || last?.innerText || '').trim().slice(0, 200),
};
