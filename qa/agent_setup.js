// ARGS: { folder, attach } — switch to Agent mode and authorize a folder (and optionally
// attach one file) through the Agent desk's own typed-path forms, exactly as a user would.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const setValue = (el, v) => { const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, v); el.dispatchEvent(new Event('input', { bubbles: true })); };
const agentBtn = document.querySelector('.agent-mode-toggle');
if (!agentBtn) return { error: 'Agent toggle not found' };
if (agentBtn.getAttribute('aria-pressed') !== 'true') { agentBtn.click(); await sleep(1500); }
if (!document.querySelector('.agent-workspace-panel')) { document.querySelector('button[title="Workspace context"]')?.click(); await sleep(1000); }
document.querySelector('.agent-access-details')?.setAttribute('open', '');
await sleep(300);
const out = { agentPressed: agentBtn.getAttribute('aria-pressed') };
const folderInput = document.querySelector('#agent-workspace-path');
if (ARGS.folder && folderInput) {
  setValue(folderInput, ARGS.folder); await sleep(200);
  folderInput.closest('form').querySelector('button[type="submit"]').click(); await sleep(2500);
  out.authorizeConfirm = [...document.querySelectorAll('.agent-workspace-panel button')].map((b) => b.innerText.trim()).filter(Boolean).slice(0, 12);
  const confirm = [...document.querySelectorAll('.agent-workspace-panel button')].find((b) => /^(Authorize|Allow|Grant|Confirm)/i.test(b.innerText.trim()) && !b.closest('form'));
  if (confirm) { confirm.click(); await sleep(2500); out.confirmed = confirm.innerText.trim(); }
}
if (ARGS.attach) {
  const details = [...document.querySelectorAll('.agent-workspace-panel details summary')].find((s) => /Attach a file by path/i.test(s.innerText));
  details?.parentElement?.setAttribute('open', ''); await sleep(300);
  const attach = document.querySelector('#agent-attachment-path');
  if (attach) { setValue(attach, ARGS.attach); await sleep(200); attach.closest('form').querySelector('button[type="submit"]').click(); await sleep(2500); }
  out.attachments = [...document.querySelectorAll('.attachment-strip *')].map((e) => e.innerText).filter(Boolean).slice(0, 3);
}
out.workspace = document.querySelector('.agent-workspace-path')?.innerText;
out.feedback = document.querySelector('.agent-error')?.innerText || null;
return out;
