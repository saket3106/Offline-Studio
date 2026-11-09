// Describe the real page: view, composer, chips, model status, message counts.
const q = (s) => document.querySelector(s);
return {
  view: q('.chat-workspace') ? 'chat' : (q('.workspace-heading h1')?.innerText || 'other'),
  textareas: [...document.querySelectorAll('textarea')].map((t) => ({ cls: t.className, parent: t.parentElement?.className, label: t.getAttribute('aria-label') })),
  composerWrap: q('.composer-wrap')?.className || null,
  chips: [...document.querySelectorAll('.composer-chip')].map((b) => b.innerText),
  voiceBar: !!q('.voice-bar'), messages: document.querySelectorAll('.message-row').length,
  statusbar: q('.runtime-statusbar')?.innerText,
  theme: document.documentElement.dataset.theme,
};
