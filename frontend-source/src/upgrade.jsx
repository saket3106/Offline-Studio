import React, { useState, useEffect, useRef } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { X, Copy, Check, ChevronDown } from "lucide-react";
import { SelectField } from "./controls.jsx";
import {
  readUI,
  writeUI,
  applyLocalDisplay,
  useUIState,
  useVirtualGrid,
} from "./uiState.js";
import notices from "./frontendNotices.json";

// One Dark / Light / System control at the top of Appearance. The choice is local; the resolved
// dark/light is also saved through the desktop (window frame colour).
export function ThemeSegment({ onTheme }) {
  const [mode, setMode] = useState(() => readUI("themeMode", document.documentElement.dataset.theme || "dark"));
  useEffect(() => {
    const sync = () => setMode(readUI("themeMode", document.documentElement.dataset.theme || "dark"));
    window.addEventListener("offline-studio-display", sync);
    return () => window.removeEventListener("offline-studio-display", sync);
  }, []);
  const update = (k, v, set) => { writeUI(k, v); set(v); applyLocalDisplay(); };
  // One theme control: the choice is local; the resolved dark/light is also saved for the window frame.
  const chooseTheme = (v) => {
    update("themeMode", v, setMode);
    window.dispatchEvent(new Event("offline-studio-display"));
    onTheme?.(document.documentElement.dataset.theme === "light" ? "light" : "dark");
  };
  return (
    <div className="theme-segment-row">
        <span id="theme-segment-label">Theme</span>
        <div className="theme-segment" role="radiogroup" aria-labelledby="theme-segment-label"
          onKeyDown={(e) => {
            const order = ["dark", "light", "auto"], at = Math.max(0, order.indexOf(mode));
            const step = e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
            if (!step) return;
            e.preventDefault(); const next = order[(at + step + order.length) % order.length]; chooseTheme(next);
            e.currentTarget.querySelector(`[data-value="${next}"]`)?.focus();
          }}>
          {[["dark", "Dark"], ["light", "Light"], ["auto", "System"]].map(([v, t]) => (
            <button key={v} type="button" role="radio" data-value={v} aria-checked={mode === v} tabIndex={mode === v || (!["dark","light","auto"].includes(mode) && v === "dark") ? 0 : -1}
              className={mode === v ? "is-active" : ""} onClick={() => chooseTheme(v)}>{t}</button>
          ))}
        </div>
      </div>
  );
}

export function LocalDisplayPreferences() {
  const [mode, setMode] = useState(() =>
      readUI("themeMode", document.documentElement.dataset.theme || "dark"),
    ),
    [zoom, setZoom] = useState(() => readUI("zoom", 1)),
    [developer, setDeveloper] = useState(() => readUI("developer", false));
  // Color theme (above), the header toggle and this control share one
  // local theme mode; refresh when either of the others changes it.
  useEffect(() => {
    const sync = () =>
      setMode(readUI("themeMode", document.documentElement.dataset.theme || "dark"));
    window.addEventListener("offline-studio-display", sync);
    return () => window.removeEventListener("offline-studio-display", sync);
  }, []);
  const update = (k, v, set) => {
    writeUI(k, v);
    set(v);
    applyLocalDisplay();
  };
  return (
    <section className="local-display-preferences">
      <h3>Display & advanced</h3>
      <p>These interface-only preferences are saved on this computer.</p>
      <label>
        UI zoom · {Math.round(zoom * 100)}%
        <input
          aria-label="UI zoom"
          type="range"
          min=".8"
          max="1.5"
          step=".05"
          value={zoom}
          onChange={(e) => update("zoom", Number(e.target.value), setZoom)}
        />
      </label>
      <label className="switch-label">
        <input
          type="checkbox"
          role="switch"
          checked={developer}
          onChange={(e) => update("developer", e.target.checked, setDeveloper)}
        />
        Developer details{" "}
        <small>
          Show technical response measurements when you open Details.
        </small>
      </label>
    </section>
  );
}
export function DiagnosticValue({ value }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const text = String(value),
    long = text.length > 48;
  return (
    <dd>
      <span className={long ? "diagnostic-hash" : ""} title={text}>
        {long ? text.slice(0, 14) + "…" + text.slice(-12) : text}
      </span>
      {long && (
        <button
          className="icon-button"
          type="button"
          aria-label="Copy full diagnostic value"
          title="Copy full value"
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              clearTimeout(timer.current);
              timer.current = setTimeout(() => setCopied(false), 1500);
            } catch {
              setCopied(false);
            }
          }}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
      )}
    </dd>
  );
}
export function ResponseDrawer({ open, onClose, children }) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-overlay" />
        <Dialog.Popup className="response-drawer">
          <header>
            <Dialog.Title>Response details</Dialog.Title>
            <Dialog.Close
              className="icon-button"
              aria-label="Close response details"
            >
              <X size={18} />
            </Dialog.Close>
          </header>
          <Dialog.Description>
            Measurements supplied by the local runtime. Unavailable values are
            omitted.
          </Dialog.Description>
          <section className="response-details">{children}</section>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function SourceChip({ children, count }) {
  return (
    <details className="memory-sources">
      <summary>
        {count} sources <ChevronDown size={14} />
      </summary>
      <div className="source-chip-popup">{children}</div>
    </details>
  );
}
export function PanelResizeHandle({
  variable = "--inspector-width",
  storageKey = "inspectorWidth",
  min = 290,
  max = 560,
  side = "left",
}) {
  const [currentWidth, setCurrentWidth] = useState(() =>
    readUI(storageKey, min),
  );
  const update = (v) => {
    const next = Math.max(min, Math.min(max, v));
    document.documentElement.style.setProperty(variable, next + "px");
    writeUI(storageKey, next);
    setCurrentWidth(next);
  };
  useEffect(() => {
    document.documentElement.style.setProperty(
      variable,
      Math.max(min, Math.min(max, Number(readUI(storageKey, min)))) + "px",
    );
  }, [variable, storageKey, min, max]);
  return (
    <div
      className="panel-resize"
      role="separator"
      aria-label={side === "left" ? "Resize context panel" : "Resize sidebar"}
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={currentWidth}
      tabIndex={0}
      onKeyDown={(e) => {
        if (["ArrowLeft", "ArrowRight"].includes(e.key)) {
          e.preventDefault();
          update(
            parseInt(
              getComputedStyle(document.documentElement).getPropertyValue(
                variable,
              ),
            ) +
              (e.key === "ArrowLeft" ? 16 : -16) * (side === "left" ? 1 : -1),
          );
        }
      }}
      onPointerDown={(e) => {
        const start = e.clientX,
          width = parseInt(
            getComputedStyle(document.documentElement).getPropertyValue(
              variable,
            ),
          );
        const target = e.currentTarget;
        target.setPointerCapture(e.pointerId);
        target.onpointermove = (move) =>
          update(width + (start - move.clientX) * (side === "left" ? 1 : -1));
        const stop = () => {
          target.onpointermove = null;
          target.onpointerup = null;
          target.onpointercancel = null;
        };
        target.onpointerup = stop;
        target.onpointercancel = stop;
      }}
    />
  );
}
export function VirtualChatList({ groups, chats, filter, renderRow, empty }) {
  const [closed, setClosed] = useUIState("closedChatGroups", []);
  const ref = useRef(null);
  const rows = filter
    ? chats.map((chat) => ({ chat }))
    : groups.flatMap((group) => [
        { group: group.title, count: group.items.length },
        ...(closed.includes(group.title)
          ? []
          : group.items.map((chat) => ({ chat }))),
      ]);
  const view = useVirtualGrid(rows.length, ref, {
    minWidth: 100000,
    rowHeight: 38,
    overscan: 4,
  });
  return (
    <div className="history-scroll">
      <div
        ref={ref}
        className="history-viewport virtual-history"
        tabIndex={0}
        aria-label="Recent chats"
        onKeyDown={(e) => {
          if (e.target !== ref.current) return;
          if (e.key === "Home") {
            e.preventDefault();
            ref.current.scrollTop = 0;
          }
          if (e.key === "End") {
            e.preventDefault();
            ref.current.scrollTop = ref.current.scrollHeight;
          }
        }}
      >
        {!rows.length ? (
          <div className="empty-history">{empty}</div>
        ) : (
          <div style={{ height: view.height, position: "relative" }}>
            {rows.slice(view.start, view.end).map((row, i) => (
              <div
                key={row.group || row.chat.id}
                style={{
                  position: "absolute",
                  top: (view.start + i) * 38,
                  left: 0,
                  right: 0,
                  height: 38,
                }}
              >
                {row.group ? (
                  <button
                    className="history-category-title history-group-toggle"
                    aria-expanded={!closed.includes(row.group)}
                    onClick={() =>
                      setClosed((old) =>
                        old.includes(row.group)
                          ? old.filter((k) => k !== row.group)
                          : [...old, row.group],
                      )
                    }
                  >
                    <ChevronDown
                      size={14}
                      style={{
                        transform: closed.includes(row.group)
                          ? "rotate(-90deg)"
                          : undefined,
                      }}
                    />
                    {row.group}
                    <span>{row.count}</span>
                  </button>
                ) : (
                  renderRow(row.chat)
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
export function AboutDialog({ open, onClose }) {
  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-overlay" />
        <Dialog.Popup className="command-dialog about-dialog">
          <header>
            <Dialog.Title>Offline Studio</Dialog.Title>
            <Dialog.Close className="icon-button" aria-label="Close About">
              <X size={18} />
            </Dialog.Close>
          </header>
          <Dialog.Description>
            A private, local desktop workspace for thinking, writing and
            creating.
          </Dialog.Description>
          <h3>Frontend licences</h3>
          <div className="frontend-notices">
            {notices.map((n) => (
              <details key={n.name}>
                <summary>
                  {n.name} {n.version} · {n.license}
                </summary>
                <pre>{n.text}</pre>
              </details>
            ))}
          </div>
          <p>
            These are direct frontend dependency notices. Transitive components,
            Python, Qt/PySide6, native engines and models remain subject to
            their separate retained notices and distribution review.
          </p>
          <button className="secondary-button" onClick={onClose}>
            Done
          </button>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
