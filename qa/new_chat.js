// Start a new chat through the real sidebar button; return the composer state.
const button = document.querySelector('.new-chat-button');
if (!button) return { error: 'new chat button not found' };
button.click();
await new Promise((r) => setTimeout(r, 1500));
return { messages: document.querySelectorAll('.message-row').length, composer: !!document.querySelector('.composer-shell textarea'), mode: document.querySelector('.mode-chip')?.innerText };
