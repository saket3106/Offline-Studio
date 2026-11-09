// Click the newest answer's Continue action; report what it put in the composer.
const msgs = document.querySelectorAll('.assistant-message');
const button = msgs[msgs.length - 1]?.querySelector('.response-footnote .text-action');
if (!button) return { error: 'Continue not shown' };
button.click();
await new Promise((r) => setTimeout(r, 800));
const ta = document.querySelector('.composer-shell textarea');
return { composerValue: ta?.value, focused: document.activeElement === ta };
