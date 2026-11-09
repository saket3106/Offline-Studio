// ARGS: { chatTitle } — open a chat from the sidebar, press Read aloud on its last answer,
// and time "click → Reading aloud" (first audio as shown by the real player), then stop.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
[...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === 'Chats')?.click(); await sleep(800);
const row = [...document.querySelectorAll('.history-item')].find((b) => b.innerText.trim().toLowerCase().startsWith(ARGS.chatTitle.toLowerCase()));
if (!row) return { error: 'chat not found' };
row.click(); await sleep(2500);
const msgs = document.querySelectorAll('.assistant-message'); const last = msgs[msgs.length - 1];
const button = last?.querySelector('button[aria-label="Read aloud offline"]');
if (!button) return { error: 'read aloud button not found' };
const t0 = performance.now(); button.click();
let loadingSeen = null, speaking = null, states = [];
for (let i = 0; i < 300; i++) {
  await sleep(50);
  const status = document.querySelector('.speech-player .speech-player-status')?.innerText?.trim();
  if (status && states[states.length - 1] !== status) states.push(status);
  if (status === 'Preparing voice…' && loadingSeen === null) loadingSeen = Math.round(performance.now() - t0);
  if (status === 'Reading aloud') { speaking = Math.round(performance.now() - t0); break; }
}
const playerWidth = Math.round(document.querySelector('.speech-player')?.getBoundingClientRect().width || 0);
const settingsVisible = !!document.querySelector('.speech-player .speech-player-settings') && getComputedStyle(document.querySelector('.speech-player .speech-player-settings')).display !== 'none';
await sleep(1500);
const stop = [...document.querySelectorAll('.speech-player button')].find((b) => /stop speech/i.test(b.getAttribute('title') || b.getAttribute('aria-label') || ''));
const tStop = performance.now(); stop?.click();
let stopped = null;
for (let i = 0; i < 100; i++) { await sleep(20); if (!document.querySelector('.speech-player')) { stopped = Math.round(performance.now() - tStop); break; } }
return { firstAudioMs: speaking, loadingShownMs: loadingSeen, states, playerWidth, settingsVisible, stopToHiddenMs: stopped };
