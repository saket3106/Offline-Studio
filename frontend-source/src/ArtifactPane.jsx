import React, { useEffect, useMemo, useRef, useState } from "react";
import { CodeXml, Columns2, Eye, RotateCw, X } from "lucide-react";
import { PanelResizeHandle } from "./upgrade.jsx";

// Languages the pane can render. Everything else still opens, as code only.
const PREVIEWABLE = new Set(["html", "htm", "svg", "xml"]);
export function canPreview(lang, source = "") {
  const l = String(lang || "").toLowerCase();
  if (l === "xml") return /^\s*(<\?xml[^>]*>\s*)?<svg[\s>]/i.test(source);
  return PREVIEWABLE.has(l);
}

/** Ask the shell to show a code artifact beside the chat. */
export function openArtifact(detail) {
  window.dispatchEvent(new CustomEvent("studio:artifact", { detail }));
}

// The preview runs in an opaque-origin sandbox (no same-origin, no network): scripts may run
// inside the frame, but they cannot reach the app, the bridge, files, or the internet.
const CSP = "default-src 'none'; img-src data: blob:; media-src data: blob:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; font-src data:";
export function previewDocument(lang, source) {
  const meta = `<meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="${CSP}"><meta name="viewport" content="width=device-width,initial-scale=1">`;
  const l = String(lang || "").toLowerCase();
  if (l === "svg" || l === "xml") {
    return `<!doctype html><html><head>${meta}<style>html,body{margin:0;height:100%;background:#fff}body{display:grid;place-items:center}svg{max-width:100%;max-height:100vh;height:auto}</style></head><body>${source}</body></html>`;
  }
  const text = String(source || "");
  if (/<head[\s>]/i.test(text)) return text.replace(/<head([^>]*)>/i, `<head$1>${meta}`);
  if (/<html[\s>]/i.test(text)) return text.replace(/<html([^>]*)>/i, `<html$1><head>${meta}</head>`);
  return `<!doctype html><html><head>${meta}</head><body>${text}</body></html>`;
}

const VIEWS = [["preview", "Preview", Eye], ["code", "Code", CodeXml], ["split", "Split", Columns2]];

export function ArtifactPane({ onOpen }) {
  const [artifact, setArtifact] = useState(null);
  const [view, setView] = useState("preview");
  const [reload, setReload] = useState(0);
  const pane = useRef(null);
  const returnFocus = useRef(null);
  useEffect(() => {
    const show = (event) => {
      const d = event.detail || {};
      returnFocus.current = document.activeElement;
      setArtifact({ lang: String(d.lang || "").toLowerCase(), source: String(d.source || ""), title: d.title || "" });
      setView(canPreview(d.lang, d.source) ? "preview" : "code");
      setReload((n) => n + 1);
      onOpen?.();
      requestAnimationFrame(() => pane.current?.querySelector(".artifact-views [aria-checked=true]")?.focus());
    };
    const hide = () => setArtifact(null);
    window.addEventListener("studio:artifact", show);
    window.addEventListener("studio:artifact-close", hide);
    return () => { window.removeEventListener("studio:artifact", show); window.removeEventListener("studio:artifact-close", hide); };
  }, [onOpen]);
  const previewable = artifact && canPreview(artifact.lang, artifact.source);
  const doc = useMemo(() => (previewable ? previewDocument(artifact.lang, artifact.source) : ""), [artifact, previewable]);
  const close = () => {
    setArtifact(null);
    const back = returnFocus.current;
    if (back && document.contains(back)) requestAnimationFrame(() => back.focus());
  };
  if (!artifact) return null;
  const views = previewable ? VIEWS : VIEWS.filter(([v]) => v === "code");
  const lines = artifact.source.split("\n").length;
  const label = (artifact.lang || "code").toUpperCase();
  return (
    <aside ref={pane} className={"artifact-pane view-" + view} aria-label="Code preview"
      onKeyDown={(e) => { if (e.key === "Escape" && !e.defaultPrevented) { e.preventDefault(); close(); } }}>
      <PanelResizeHandle variable="--artifact-width" storageKey="artifactWidth" min={440} max={1100} side="left" />
      <header className="artifact-header">
        <div className="artifact-title">
          <strong>{artifact.title || (previewable ? "Live preview" : "Code")}</strong>
          <small>{label} · {lines} {lines === 1 ? "line" : "lines"}{previewable ? " · sandboxed, offline" : ""}</small>
        </div>
        <div className="artifact-views" role="radiogroup" aria-label="Pane layout"
          onKeyDown={(e) => {
            const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
            if (!step) return;
            e.preventDefault();
            const order = views.map(([v]) => v), next = order[(order.indexOf(view) + step + order.length) % order.length];
            setView(next); e.currentTarget.querySelector(`[data-view="${next}"]`)?.focus();
          }}>
          {views.map(([v, text, Icon]) => (
            <button key={v} type="button" role="radio" data-view={v} aria-checked={view === v} tabIndex={view === v ? 0 : -1}
              className={view === v ? "is-active" : ""} onClick={() => setView(v)} title={text}>
              <Icon size={14} aria-hidden="true" /><span>{text}</span>
            </button>
          ))}
        </div>
        {previewable && <button type="button" className="artifact-icon" onClick={() => setReload((n) => n + 1)} title="Reload preview" aria-label="Reload preview"><RotateCw size={15} /></button>}
        <button type="button" className="artifact-icon" onClick={close} title="Close preview (Esc)" aria-label="Close preview"><X size={16} /></button>
      </header>
      <div className="artifact-body">
        {previewable && view !== "code" && (
          <iframe key={reload} className="artifact-frame" title={`${label} preview`} sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={doc} />
        )}
        {view !== "preview" && (
          <pre className="artifact-code" tabIndex={0} aria-label={`${label} source`}><code>{artifact.source}</code></pre>
        )}
      </div>
    </aside>
  );
}
