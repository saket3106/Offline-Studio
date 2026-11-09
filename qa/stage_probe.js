const stage = document.querySelector('.studio-stage');
const r = (e) => { const b = e.getBoundingClientRect(); return [Math.round(b.x), Math.round(b.y), Math.round(b.width), Math.round(b.height)]; };
return {
  stage: stage && { rect: r(stage), position: getComputedStyle(stage).position, overflow: getComputedStyle(stage).overflow, display: getComputedStyle(stage).display },
  children: [...(stage?.children || [])].map((e) => { const s = getComputedStyle(e); return { tag: e.tagName, cls: e.className, rect: r(e), position: s.position, display: s.display, opacity: s.opacity, visibility: s.visibility, zIndex: s.zIndex, natural: [e.naturalWidth, e.naturalHeight], src: (e.currentSrc || e.src || '').slice(-60) }; }),
};
