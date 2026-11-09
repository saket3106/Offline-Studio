// ARGS: { mode: 'Offline'|'Web'|'Smart Hybrid' } — use the real composer mode chip.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const chip = document.querySelector('.mode-chip');
if (!chip) return { error: 'mode chip not found' };
chip.click(); await sleep(400);
const item = [...document.querySelectorAll('.mode-chip-menu [role="menuitemradio"]')].find((b) => b.getAttribute('aria-label') === ARGS.mode);
if (!item) return { error: 'mode not in menu', items: [...document.querySelectorAll('.mode-chip-menu button')].map((b) => b.getAttribute('aria-label')) };
item.click(); await sleep(1200);
return { chip: document.querySelector('.mode-chip')?.innerText.trim() };
