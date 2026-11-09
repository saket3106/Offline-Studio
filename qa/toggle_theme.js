// Click the real header theme button; return the theme before/after.
const before = document.documentElement.dataset.theme;
const button = document.querySelector('button[aria-label^="Switch to"]');
if (!button) return { error: 'theme button not found' };
const label = button.getAttribute('aria-label');
button.click();
await new Promise((r) => setTimeout(r, 1200));
return { before, clicked: label, after: document.documentElement.dataset.theme };
