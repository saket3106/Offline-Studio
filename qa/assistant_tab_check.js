// ARGS: { commands: [..], timeoutMs } — open the Assistant tab, run each command through the real
// command box, wait for the run to finish (or wait for confirmation), and report the run cards.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nav = [...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === 'Assistant');
if (!nav) return { error: 'Assistant nav item not found' };
nav.click(); await sleep(600);
const input = document.querySelector('input[aria-label="Tell the assistant what to do"]');
if (!input) return { error: 'command box not found' };
const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
const results = [];
for (const command of ARGS.commands) {
  const before = document.querySelectorAll('.assistant-run').length;
  setter.call(input, command); input.dispatchEvent(new Event('input', { bubbles: true })); await sleep(80);
  const t0 = performance.now();
  input.closest('form').requestSubmit();
  let card = null;
  const end = performance.now() + (ARGS.timeoutMs || 60000);
  while (performance.now() < end) {
    await sleep(100);
    if (document.querySelectorAll('.assistant-run').length > before) {
      card = document.querySelector('.assistant-run');
      if (/is-(done|error|awaiting|cancelled)/.test(card.className)) break;
    }
  }
  results.push({ command, ms: Math.round(performance.now() - t0), cls: card?.className, meta: card?.querySelector('.assistant-run-meta')?.innerText,
    steps: [...(card?.querySelectorAll('.assistant-step') || [])].map((s) => s.className.replace('assistant-step ', '') + ' | ' + s.innerText.replace(/\s+/g, ' ').slice(0, 160)),
    reply: card?.querySelector('.assistant-run-reply')?.innerText });
}
return { tiles: document.querySelectorAll('.assistant-tile').length, results };
