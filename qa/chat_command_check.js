// ARGS: { text } — type a command in the chat composer and report the assistant run shown above it
// (instead of waiting for a chat answer), plus whether a chat message was created.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
[...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === 'Chats')?.click(); await sleep(800);
const ta = document.querySelector('.composer-shell textarea');
if (!ta) return { error: 'composer not found' };
const before = document.querySelectorAll('.message-row').length;
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, ARGS.text); ta.dispatchEvent(new Event('input', { bubbles: true })); await sleep(120);
const t0 = performance.now();
ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
let run = null;
for (let i = 0; i < 150; i++) {
  await sleep(100);
  run = document.querySelector('.chat-composer-slot .assistant-run');
  if (run && /is-(done|error|awaiting)/.test(run.className)) break;
}
return { ms: Math.round(performance.now() - t0), run: run ? run.className + ' | ' + run.innerText.replace(/\s+/g, ' ').slice(0, 200) : null,
  chatMessagesAdded: document.querySelectorAll('.message-row').length - before };
