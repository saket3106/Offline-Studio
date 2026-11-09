// ARGS: { seconds } — new chat, start Live Voice, record bar state transitions, turns and title
// while a human speaks; end voice at the end. Content of speech is not stored beyond the chat itself.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.querySelector('.new-chat-button')?.click(); await sleep(1800);
const start = document.querySelector('button[aria-label="Start Live Voice"]');
if (!start) return { error: 'Start Live Voice not found' };
const t0 = performance.now(); start.click();
const ms = () => Math.round(performance.now() - t0);
const timeline = []; let lastState = null, lastLabel = null;
const snapshotMessages = () => [...document.querySelectorAll('.message-row')].map((m) => ({ role: m.classList.contains('user-message') ? 'user' : 'assistant', text: (m.querySelector('.assistant-markdown, .user-bubble')?.innerText || '').trim() }));
let lastCount = 0; const turns = [];
for (let i = 0; i < (ARGS.seconds || 150) * 20; i++) {
  await sleep(50);
  const bar = document.querySelector('.voice-bar');
  const state = bar?.getAttribute('data-state') || (bar ? '?' : 'no-bar');
  const label = document.querySelector('.voice-bar-state')?.innerText?.trim();
  if (state !== lastState || label !== lastLabel) { timeline.push({ ms: ms(), state, label }); lastState = state; lastLabel = label; }
  const msgs = snapshotMessages();
  if (msgs.length !== lastCount) { turns.push({ ms: ms(), count: msgs.length, last: msgs[msgs.length - 1]?.role }); lastCount = msgs.length; }
}
const messages = snapshotMessages().map((m) => ({ role: m.role, words: (m.text.match(/\b[\w'’-]+\b/g) || []).length, text: m.text.slice(0, 160) }));
window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await sleep(1500);
const title = document.querySelector('.history-row.active .history-item')?.innerText?.trim() || document.querySelector('.topbar-title, header [class*="title"]')?.innerText?.trim();
return { timeline, turns, messages, title, ended: !document.querySelector('.voice-bar') };
