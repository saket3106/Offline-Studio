// Runs inside the real Offline Studio page (via qa/cdp.mjs evalfile). Web-grounding check.
// ARGS: { text, mode: 'Web'|'Smart Hybrid', timeoutMs }
// New chat -> composer mode chip -> send -> approve the web-permission card for this exact request
// -> wait for the answer. Reports the answer, citations and whether it refused web access.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const timeout = ARGS.timeoutMs || 240000;
document.querySelector('.new-chat-button')?.click(); await sleep(1200);
const chip = document.querySelector('.mode-chip');
if (chip) { chip.click(); await sleep(400); [...document.querySelectorAll('.mode-chip-menu [role="menuitemradio"]')].find((b) => b.getAttribute('aria-label') === (ARGS.mode || 'Web'))?.click(); await sleep(1200); }
const ta = document.querySelector('.composer-shell textarea');
if (!ta) return { error: 'composer not found' };
const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
setter.call(ta, ARGS.text); ta.dispatchEvent(new Event('input', { bubbles: true })); await sleep(150);
const sent = performance.now();
ta.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true, cancelable: true }));
let approved = false, permissionText = '';
const busy = () => !!document.querySelector('.send-button.stop-button');
while (performance.now() - sent < timeout) {
  await sleep(250);
  if (!approved) {
    const button = [...document.querySelectorAll('button')].find((b) => /^(allow|approve|allow once|search|continue)\b/i.test(b.innerText.trim()) && b.closest('[class*="permission"],[class*="research"],[class*="intelligence"],[role="dialog"],[class*="approval"]'));
    if (button) { permissionText = (button.closest('[class*="permission"],[class*="research"],[class*="intelligence"],[role="dialog"],[class*="approval"]')?.innerText || '').slice(0, 300); button.click(); approved = true; continue; }
  }
  const msgs = document.querySelectorAll('.assistant-message'); const last = msgs[msgs.length - 1];
  const md = last?.querySelector('.assistant-markdown');
  if (performance.now() - sent > 4000 && !busy() && md && !md.classList.contains('streaming-active') && md.innerText.trim().length > 20) break;
}
await sleep(800);
const msgs = document.querySelectorAll('.assistant-message'); const last = msgs[msgs.length - 1];
const answer = (last?.querySelector('.assistant-markdown')?.innerText || last?.innerText || '').trim();
const links = [...(last?.querySelectorAll('a[href^="http"]') || [])].map((a) => a.href);
return { ms: Math.round(performance.now() - sent), approved, permissionText, chip: document.querySelector('.mode-chip')?.innerText.trim(),
  refused: /can(?:no|')t (?:access|browse|verify)|untrusted|do not have (?:internet|web)|unable to (?:access|browse)/i.test(answer),
  citations: links.length, words: answer.split(/\s+/).length, answer: answer.slice(0, 1500), sources: last?.querySelector('[class*="research"],[class*="source"]')?.innerText.slice(0, 300) || '' };
