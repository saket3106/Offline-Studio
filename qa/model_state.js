// ARGS: { action: 'unload'|'load'|null } — act on the real Models page and compare it with the status bar.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nav = [...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === 'Models');
nav?.click(); await sleep(2500);
const read = () => ({
  page: document.querySelector('.model-manager-guidance')?.innerText,
  loadedBadge: [...document.querySelectorAll('.model-manager-item')].filter((c) => c.querySelector('.status-badge.is-loaded')).map((c) => c.querySelector('strong')?.innerText),
  statusbar: document.querySelector('.runtime-statusbar button')?.innerText,
});
const before = read();
if (ARGS.action) {
  const label = ARGS.action === 'unload' ? 'Unload runtime' : 'Load default';
  const button = [...document.querySelectorAll('.model-manager-toolbar button')].find((b) => b.innerText.trim() === label);
  if (!button || button.disabled) return { before, error: label + ' unavailable' };
  button.click();
  for (let i = 0; i < 120; i++) { await sleep(500); if (!document.querySelector('.model-manager[aria-busy="true"]')) break; }
  await sleep(1500);
}
return { before, after: read() };
