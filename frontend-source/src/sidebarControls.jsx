import React, { useEffect, useRef, useState } from "react";
import { Check, X, Trash2, CheckSquare, RotateCcw, Download } from "lucide-react";

/** Inline chat rename: Enter saves, Esc cancels, an empty name is rejected. */
export function ChatRenameInput({ initial = "", onSave, onCancel }) {
  const [value, setValue] = useState(initial);
  const [invalid, setInvalid] = useState(false);
  const input = useRef(null);
  useEffect(() => { input.current?.focus(); input.current?.select(); }, []);
  const save = (fromBlur = false) => {
    const clean = value.trim();
    if (!clean) {
      if (fromBlur) { onCancel?.(); return; }
      setInvalid(true); input.current?.focus(); return;
    }
    if (clean === String(initial).trim()) { onCancel?.(); return; }
    onSave?.(clean);
  };
  return <div className="history-rename-wrap" onClick={(e) => e.stopPropagation()}>
    <input
      ref={input}
      className="history-rename-input"
      aria-label="Chat name"
      aria-invalid={invalid || undefined}
      aria-describedby={invalid ? "chat-rename-error" : undefined}
      value={value}
      maxLength={70}
      onChange={(e) => { setValue(e.target.value); if (invalid) setInvalid(false); }}
      onKeyDown={(e) => {
        if (e.key === "Enter") { e.preventDefault(); save(false); }
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onCancel?.(); }
      }}
      onBlur={() => save(true)}
    />
    <button type="button" className="history-rename-btn" aria-label="Save name" title="Save (Enter)" onMouseDown={(e) => { e.preventDefault(); save(false); }}><Check size={13} /></button>
    <button type="button" className="history-rename-btn" aria-label="Cancel rename" title="Cancel (Esc)" onMouseDown={(e) => { e.preventDefault(); onCancel?.(); }}><X size={13} /></button>
    {invalid && <span id="chat-rename-error" className="history-rename-error" role="alert">Name can't be empty</span>}
  </div>;
}

/** Bulk selection bar: count, Select all / Clear, Delete (or Restore), Export, Cancel. */
export function ChatBulkBar({ count = 0, total = 0, busy = false, trashMode = false, onSelectAll, onClear, onDelete, onExport, onCancel }) {
  const bar = useRef(null);
  const all = total > 0 && count >= total;
  useEffect(() => { bar.current?.querySelector("button")?.focus(); }, []);
  return <section
    ref={bar}
    className="chat-bulk-bar"
    role="toolbar"
    aria-label="Selected conversations"
    onKeyDown={(e) => {
      if (e.key === "Escape") { e.preventDefault(); onCancel?.(); return; }
      if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
      const buttons = [...e.currentTarget.querySelectorAll("button:not(:disabled)")];
      const index = buttons.indexOf(document.activeElement);
      if (index < 0) return;
      e.preventDefault();
      buttons[(index + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
    }}
  >
    <span className="chat-bulk-count" role="status" aria-live="polite"><strong>{count}</strong> selected</span>
    <div className="chat-bulk-actions">
      <button type="button" className="chat-bulk-btn" disabled={busy || !total} onClick={all ? onClear : onSelectAll} aria-label={all ? "Clear selection" : "Select all conversations"} title={all ? "Clear selection" : "Select all"}><CheckSquare size={14} /><span>{all ? "Clear" : "Select all"}</span></button>
      {onExport && <button type="button" className="chat-bulk-btn" disabled={!count} onClick={onExport} aria-label="Export selected conversations" title="Export selected"><Download size={14} /></button>}
      <button type="button" className="chat-bulk-btn is-danger" disabled={busy || !count} onClick={onDelete} aria-label={trashMode ? `Restore ${count} selected conversations` : `Delete ${count} selected conversations`} title={trashMode ? "Restore selected" : "Delete selected"}>{trashMode ? <RotateCcw size={14} /> : <Trash2 size={14} />}<span>{trashMode ? "Restore" : "Delete"}</span></button>
      <button type="button" className="chat-bulk-btn" onClick={onCancel} aria-label="Cancel selection" title="Cancel (Esc)"><X size={14} /></button>
    </div>
  </section>;
}
