// ARGS: { page: 'models'|'studio'|'library'|'knowledge'|'chat' }
// Navigate with the real sidebar, wait, and report what the fixes should show.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const nav = { chat: 'Chats', models: 'Models', studio: 'Image Studio', library: 'Library', knowledge: 'Knowledge' }[ARGS.page];
const button = [...document.querySelectorAll('.side-primary .nav-item')].find((b) => b.innerText.trim() === nav);
if (!button) return { error: 'nav item not found: ' + nav };
button.click(); await sleep(ARGS.wait || 3500);
const q = (s) => document.querySelector(s), qa = (s) => [...document.querySelectorAll(s)];
const out = { page: ARGS.page, theme: document.documentElement.dataset.theme, selectedNav: qa('.side-primary .nav-item.selected').map((b) => b.innerText.trim()) };
const imgOk = (img) => img.complete && img.naturalWidth > 0;
if (ARGS.page === 'models') {
  out.guidance = q('.model-manager-guidance')?.innerText;
  out.cards = qa('.model-manager-item').map((c) => ({ name: c.querySelector('strong')?.innerText, badges: [...c.querySelectorAll('.status-badge')].map((b) => b.innerText.trim()), currentDefault: !!c.querySelector('.is-current') }));
  out.statusbar = q('.runtime-statusbar')?.innerText.split('\n')[0];
}
if (ARGS.page === 'studio') {
  const thumbs = qa('.studio-recent img');
  out.thumbs = thumbs.length; out.thumbsLoaded = thumbs.filter(imgOk).length;
  const stage = qa('.studio-stage img'); out.stageImages = stage.map((i) => ({ cls: i.className, loaded: imgOk(i) }));
  out.generateButton = q('.studio-generate')?.innerText.trim(); out.chips = qa('.studio-aspect-chips .studio-chip').length;
  out.referencesSubtitle = q('.knowledge-studio .workspace-heading p')?.innerText; out.devStringsVisible = qa('.dev-only').filter((e) => e.offsetParent).length;
}
if (ARGS.page === 'library') {
  out.countTexts = qa('.workspace-view *').filter((e) => e.children.length === 0 && /\b\d[\d,]*\s+images?\b/i.test(e.innerText || '') && e.offsetParent).map((e) => e.innerText.trim()).slice(0, 6);
  const cards = qa('.library-grid-scroll img').slice(0, 20); out.cardImages = cards.length; out.cardImagesLoaded = cards.filter(imgOk).length;
}
if (ARGS.page === 'knowledge') {
  out.status = q('.knowledge-status')?.innerText; out.devStringsVisible = qa('.dev-only').filter((e) => e.offsetParent).map((e) => e.innerText.slice(0, 60));
  out.rawCodesVisible = (q('.knowledge-workspace')?.innerText.match(/LOCAL_ONNX_CONFIGURED|NOT_CONFIGURED_LEXICAL_ACTIVE|[A-Z]:\\[^\s]+\.onnx/g) || []).length;
}
return out;
