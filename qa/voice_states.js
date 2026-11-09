// Start Live Voice with the real composer button, record bar states for ARGS.seconds,
// exercise Mute/Unmute, then end with Escape. Speech itself needs a human speaker.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const start = document.querySelector('button[aria-label="Start Live Voice"]');
if (!start) return { error: 'Start Live Voice not found' };
const t0 = performance.now(); start.click();
const timeline = []; let barAt = null, listeningAt = null;
const label = () => document.querySelector('.voice-bar-state')?.innerText?.trim();
for (let i = 0; i < (ARGS.seconds || 20) * 10; i++) {
  await sleep(100);
  if (document.querySelector('.voice-bar') && barAt === null) barAt = Math.round(performance.now() - t0);
  const l = label(); if (l && timeline[timeline.length - 1]?.label !== l) timeline.push({ label: l, ms: Math.round(performance.now() - t0) });
  if (l === 'Listening' && listeningAt === null) listeningAt = Math.round(performance.now() - t0);
  if (listeningAt !== null && i > 20) break;
}
const conversationVisible = !!document.querySelector('.conversation') || !!document.querySelector('.chat-greeting');
const mute = document.querySelector('.voice-bar button[aria-label="Mute microphone"]');
mute?.click(); await sleep(1200); const afterMute = label();
document.querySelector('.voice-bar button[aria-label="Unmute microphone"]')?.click(); await sleep(1200); const afterUnmute = label();
window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })); await sleep(1500);
return { barShownMs: barAt, listeningMs: listeningAt, timeline, afterMute, afterUnmute, endedByEscape: !document.querySelector('.voice-bar'), composerBack: !!document.querySelector('.composer-shell textarea'), oldCardPresent: !!document.querySelector('.live-voice-dock, .voice-orb'), conversationVisible };
