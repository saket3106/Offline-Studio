// ARGS: { nav } — click a sidebar destination by its label and wait for it to render.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
document.querySelector('.settings-dialog [aria-label="Close settings"], .settings-dialog .close-button')?.click();
const button = [...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === ARGS.nav);
if (!button) return { error: 'not found: ' + ARGS.nav };
button.click(); await sleep(ARGS.wait || 1500);
return { ok: true, selected: document.querySelector('.side-primary .nav-item.selected')?.innerText.trim() };
