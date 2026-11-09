// Report the newest assistant answer as rendered in the real app.
const msgs = document.querySelectorAll('.assistant-message');
const last = msgs[msgs.length - 1];
if (!last) return { error: 'no assistant message' };
const md = last.querySelector('.assistant-markdown');
const answer = (md?.innerText || '').trim();
return {
  researchLine: last.querySelector('.research-line summary')?.innerText || null,
  researchSources: [...last.querySelectorAll('.research-line .research-source button')].map((b) => b.innerText.trim()).slice(0, 8),
  citationLinks: [...(md?.querySelectorAll('a') || [])].map((a) => [a.textContent, a.getAttribute('href')]).slice(0, 12),
  rawIdsLeft: (answer.match(/\bK[0-9a-f]{16}\b/g) || []).length,
  unrenderedLinks: (answer.match(/\]\(https?:/g) || []).length,
  words: (answer.match(/\b[\w'’-]+\b/g) || []).length, footnote: last.querySelector('.response-footnote')?.innerText || null,
  preview: answer.slice(0, 220),
};
