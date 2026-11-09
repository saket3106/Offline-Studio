// Click "Allow folder access" in the Agent folder approval dialog (user's own confirmation step).
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const button = [...document.querySelectorAll('.agent-folder-approval button')].find((b) => b.innerText.trim() === 'Allow folder access');
if (!button) return { error: 'approval dialog not open' };
const path = document.querySelector('.agent-folder-approval .agent-workspace-path')?.innerText;
button.click(); await sleep(2500);
return { approvedPath: path, workspace: document.querySelector('.agent-scope .agent-workspace-path')?.innerText, feedback: document.querySelector('.agent-error')?.innerText || null };
