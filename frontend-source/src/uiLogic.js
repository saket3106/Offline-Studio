// Presentation-only policies: no filesystem access and no inferred model capabilities.
export function formatModelName(value = "") {
  const raw = String(value)
    .split(/[\\/]/)
    .pop()
    .replace(/\.gguf$/i, "");
  const quant =
    raw
      .match(
        /(?:^|[-_. ])(IQ\d[\w_]*|Q\d(?:_[A-Z0-9]+)*|F16|BF16)(?=$|[-. ])/i,
      )?.[1]
      ?.toUpperCase() || "";
  let name = raw
    .replace(/^(?:openai|qwen|google)[/_](?=[a-z])/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  name = name
    .replace(/gpt\s*oss\s*(\d+)b?/i, (_, n) => `GPT-OSS ${n}B`)
    .replace(/qwen\s*(\d(?:\.\d+)?)/i, "Qwen$1")
    .replace(/\b(\d+)b\b/gi, "$1B");
  if (quant)
    name = name
      .replace(new RegExp(quant.replaceAll("_", "[ _-]"), "i"), "")
      .trim();
  return { name: name || "No model selected", quantization: quant };
}
export const friendlyState = (value) =>
  ({
    present: "Installed",
    missing: "File missing",
    loaded: "Loaded",
    unloaded: "Not loaded",
    unsupported: "Compatibility not established",
  })[value] || value;
export function virtualRows({
  count,
  width,
  height,
  scrollTop,
  minWidth = 220,
  gap = 16,
  rowHeight = 248,
  overscan = 2,
}) {
  const columns = Math.max(
    1,
    Math.floor((Math.max(width, 1) + gap) / (minWidth + gap)),
  );
  const rows = Math.ceil(count / columns);
  const totalHeight = rows * rowHeight;
  // Filters, grouping, and chat deletion can shrink the list before the DOM
  // scroll position has been clamped by the browser. Never render an empty
  // window for a non-empty list just because the old offset is now too large.
  const visibleHeight = Math.max(0, height);
  const offset = Math.min(
    Math.max(0, Number(scrollTop) || 0),
    Math.max(0, totalHeight - visibleHeight),
  );
  const first = Math.max(0, Math.floor(offset / rowHeight) - overscan);
  const last = Math.min(
    rows,
    Math.ceil((offset + visibleHeight) / rowHeight) + overscan,
  );
  return {
    columns,
    start: first * columns,
    end: Math.min(count, last * columns),
    top: first * rowHeight,
    height: totalHeight,
    rowHeight,
  };
}

// Empty drafts are retained in SQLite for recovery, but a long run of them is
// noise in the navigation rail. Collapse only unpinned chats whose exact
// visible title is "New chat"; the current draft remains addressable and no
// record is deleted or mutated.
export function collapseDraftChats(chats = [], currentId = "") {
  if (!Array.isArray(chats)) return [];
  const drafts = chats.filter(
    chat =>
      chat &&
      !chat.pinned &&
      String(chat.title || "New chat").trim() === "New chat",
  );
  const hidden = drafts.filter(chat => chat.id !== currentId);
  if (hidden.length < 2) return chats;
  const hiddenIds = new Set(hidden.map(chat => chat.id));
  const firstHidden = chats.findIndex(chat => hiddenIds.has(chat.id));
  const group = {
    id: "__offline-studio-draft-group__",
    title: "New chat drafts",
    updated: Math.max(...hidden.map(chat => Number(chat.updated) || 0)),
    pinned: false,
    isDraftGroup: true,
    draftCount: hidden.length,
    draftIds: hidden.map(chat => chat.id),
  };
  const result = [];
  chats.forEach((chat, index) => {
    if (index === firstHidden) result.push(group);
    if (!hiddenIds.has(chat.id)) result.push(chat);
  });
  return result;
}

// Present only evidence referenced by the answer or marked as used by the
// backend. A retrieved candidate alone does not support a response claim.
export function usedMemorySources(message) {
  const sources = message?.metrics?.memory_sources;
  if (!Array.isArray(sources)) return [];
  const body = typeof message?.content === "string" ? message.content : "";
  return sources.filter(source => {
    if (!source || typeof source !== "object") return false;
    if (source.used === true) return true;
    const id = source.id;
    return typeof id === "string" && id.length > 0 && body.includes(`[${id}]`);
  });
}
export function shouldShowSources(message) {
  return usedMemorySources(message).length > 0;
}
// Stable across labels that are not unique (e.g. two chats named "Notes").
export function commandActionKey(action) {
  return action.id || action.label;
}
export function commandMatches(action, query) {
  const text = (action.label + " " + (action.keywords || "")).toLowerCase();
  return query
    .toLowerCase()
    .trim()
    .split(/\s+/)
    .every((word) => text.includes(word));
}
export const THEMES = ["dark", "light", "auto", "contrast"];
export function resolveTheme(mode, systemLight = false) {
  return mode === "auto"
    ? systemLight
      ? "light"
      : "dark"
    : mode === "contrast"
      ? "dark"
      : mode === "light"
        ? "light"
        : "dark";
}

// Research answers cite internal source IDs (K + 16 hex). Show them as numbered
// links to the recorded source and drop any ID that cannot be resolved.
const CITATION_ID = "K[0-9a-f]{16}";
export function linkCitations(text, sources = []) {
  const index = new Map();
  (sources || []).forEach((source, i) => { if (source && source.id) index.set(String(source.id), { n: i + 1, url: source.url || "" }); });
  const chip = (id, fallbackUrl = "") => {
    const found = index.get(id);
    if (!found) return "";
    const url = String(found.url || fallbackUrl || "").replace(/\(/g, "%28").replace(/\)/g, "%29").replace(/\s/g, "%20");
    return url ? `[\\[${found.n}\\]](${url})` : `[${found.n}]`;
  };
  let out = String(text || "");
  out = out.replace(new RegExp(`\\[(${CITATION_ID})\\]\\(([^)\\s]+)\\)`, "g"), (_, id, url) => chip(id, url));
  out = out.replace(new RegExp(`\\[(${CITATION_ID})\\](?!\\()`, "g"), (_, id) => chip(id));
  out = out.replace(new RegExp(`(^|[\\s(,;])(${CITATION_ID})\\b`, "g"), (_, pre, id) => pre + chip(id));
  return out.replace(/[ \t]+([.,;:!?])/g, "$1").replace(/\(\s*\)/g, "").replace(/([^\s]) {2,}/g, "$1 ");
}
