import React, { useEffect, useRef, useState } from "react";
import { AssistantCards } from "./assistantCards.jsx";
import "./assistantWorkspace.css";
import { ShieldAlert, ScrollText, Play, SkipBack, SkipForward, Volume1, Volume2, VolumeX, SunDim, Sun, Camera, FolderDown, Settings, BatteryCharging, Mic, Square } from "lucide-react";

// Assistant workspace ("Jarvis"): one command box that controls this PC through allowlisted
// tools. Everyday actions can run instantly; anything disruptive waits for Allow. Runs arrive
// as "assistantRun" events and are passed in as `runs`.

const TOOL_LABELS = {
  open_app: "Open app", close_app: "Close app", media: "Media", volume: "Volume", brightness: "Brightness",
  open_folder: "Open folder", open_settings: "Settings", screenshot: "Screenshot", timer: "Timer", system_status: "System status",
  find_files: "Find files", open_file: "Open file", lock_pc: "Lock PC", sleep_pc: "Sleep", power_mode: "Power mode", email: "Email",
};
const QUICK = [
  { label: "Play / Pause", tool: "media", args: { action: "play_pause" }, Icon: Play },
  { label: "Previous", tool: "media", args: { action: "previous" }, Icon: SkipBack },
  { label: "Next", tool: "media", args: { action: "next" }, Icon: SkipForward },
  { label: "Volume down", tool: "volume", args: { change: "down" }, Icon: Volume1 },
  { label: "Volume up", tool: "volume", args: { change: "up" }, Icon: Volume2 },
  { label: "Mute", tool: "volume", args: { change: "mute" }, Icon: VolumeX },
  { label: "Dimmer", tool: "brightness", args: { change: "down" }, Icon: SunDim },
  { label: "Brighter", tool: "brightness", args: { change: "up" }, Icon: Sun },
  { label: "Screenshot", tool: "screenshot", args: {}, Icon: Camera },
  { label: "Downloads", tool: "open_folder", args: { name: "downloads" }, Icon: FolderDown },
  { label: "Settings", tool: "open_settings", args: { page: "settings" }, Icon: Settings },
  { label: "PC status", tool: "system_status", args: {}, Icon: BatteryCharging },
];
const SUGGESTIONS = ["I feel like playing GTA 5", "Open Spotify and set the volume to 30", "Set a timer for 10 minutes",
  "Find my resume", "Turn on gaming mode", "Email sam@example.com about lunch tomorrow"];
const STATUS_TEXT = { pending: "Queued", awaiting: "Needs your OK", running: "Working…", done: "Done", error: "Failed", skipped: "Skipped" };

const RISK_TEXT = { confirm: "Changes something on this PC", high: "Hard to undo", low: "Everyday action" };
function duration(ms) { return typeof ms === "number" ? (ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`) : ""; }

/** Plain-text execution log: what was planned, each tool call with its arguments, result and time. */
export function runLog(run) {
  const lines = [];
  if (run.route) lines.push(`plan  ${run.route === "model" ? "local model" : "instant rules"}${typeof run.planMs === "number" ? ` · ${duration(run.planMs)}` : ""}`);
  (run.steps || []).forEach((s, i) => {
    const args = Object.entries(s.args || {}).filter(([, v]) => v !== "" && v != null).map(([k, v]) => `${k}=${JSON.stringify(v)}`).join(" ");
    lines.push(`${String(i + 1).padStart(2, "0")}  ${s.tool}(${args})  ${s.status}${s.decision ? ` [${s.decision}]` : ""}${s.ms != null ? ` · ${duration(s.ms)}` : ""}${s.message ? `  → ${s.message}` : ""}`);
  });
  if (typeof run.totalMs === "number") lines.push(`total ${duration(run.totalMs)} · ${run.status}`);
  return lines.join("\n");
}

function argsText(args) {
  const values = Object.entries(args || {}).filter(([, v]) => v !== "" && v !== null && v !== undefined).map(([k, v]) => (k === "request" ? `“${v}”` : String(v)));
  return values.join(" · ");
}

export function RunCard({ run, onDecide, onCancel, onOpenFile }) {
  const active = ["planning", "running", "awaiting"].includes(run.status);
  return (
    <article className={`assistant-run is-${run.status}`} aria-label={`Command: ${run.request}`}>
      <header className="assistant-run-head" title={[run.route === "model" ? "Planned by your local model" : run.route === "rules" ? "Recognized instantly" : "", typeof run.totalMs === "number" ? `${(run.totalMs / 1000).toFixed(1)} s` : ""].filter(Boolean).join(" · ")}>
        <p className="assistant-run-request">{run.request}</p>
        {active && <button className="assistant-secondary assistant-small" onClick={() => onCancel(run.id)}>Stop</button>}
      </header>
      {run.status === "planning" && <p className="assistant-run-status" role="status">Thinking about the steps…</p>}
      {!!run.steps?.length && (
        <ol className="assistant-steps">
          {run.steps.map((step, i) => (
            <li key={i} className={`assistant-step is-${step.status}`}>
              <span className="assistant-step-dot" aria-hidden="true"/>
              <div className="assistant-step-body">
                {["done", "error"].includes(step.status) && step.message
                  ? <span className={`assistant-step-result${step.status === "error" ? " is-error" : ""}`}>{step.message}{step.ms != null && <span className="assistant-step-time"> · {duration(step.ms)}</span>}</span>
                  : <>
                      <strong>{TOOL_LABELS[step.tool] || step.tool}{argsText(step.args) ? <span className="assistant-step-args"> · {argsText(step.args)}</span> : null}</strong>
                      <span className="assistant-step-state">{STATUS_TEXT[step.status] || ""}</span>
                    </>}
                {step.files?.length > 0 && (
                  <ul className="assistant-files">
                    {step.files.map((f) => <li key={f}><button className="assistant-link" title={f} onClick={() => onOpenFile(f)}>{f.split(/[\\/]/).pop()}</button><small>{f}</small></li>)}
                  </ul>
                )}
              </div>
              {step.status === "awaiting" && (
                <div className="assistant-confirm" role="group" aria-label={`Confirm ${TOOL_LABELS[step.tool] || step.tool}`}>
                  <p className="assistant-confirm-text"><ShieldAlert size={15} aria-hidden="true"/><span><strong>Needs your OK.</strong> {RISK_TEXT[step.risk] || "This action waits for you"}: {TOOL_LABELS[step.tool] || step.tool}{argsText(step.args) ? ` · ${argsText(step.args)}` : ""}. Nothing runs until you choose.</span></p>
                  <div className="assistant-step-actions">
                    <button className="assistant-primary assistant-small" onClick={() => onDecide(run.id, i, true)}>Allow</button>
                    <button className="assistant-secondary assistant-small" onClick={() => onDecide(run.id, i, false)}>Skip</button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ol>
      )}
      {run.reply && !run.steps?.some((s) => s.message && run.reply.includes(s.message)) && <p className="assistant-run-reply">{run.reply}</p>}
      {run.error && <p className="assistant-error" role="alert">{run.error}</p>}
      {!!run.steps?.length && !active && (
        <details className="assistant-log">
          <summary><ScrollText size={13} aria-hidden="true"/> Execution log{typeof run.totalMs === "number" ? ` · ${duration(run.totalMs)}` : ""}</summary>
          <pre tabIndex={0} aria-label="Execution log">{runLog(run)}</pre>
        </details>
      )}
    </article>
  );
}

export function AssistantWorkspace({ runs, onCommand, onQuick, onDecide, onCancel, onOpenFile, settings, onSettings, voiceActive, onToggleVoice, cards, cardHandlers }) {
  const [text, setText] = useState(""); const [notice, setNotice] = useState("");
  const input = useRef(null);
  useEffect(() => { input.current?.focus(); }, []);
  const submit = (value) => { const v = (value ?? text).trim(); if (!v) return; onCommand(v); setText(""); };
  const quick = async (q) => { const r = await onQuick(q.tool, q.args); setNotice(r?.ok === false ? (r.error || "That didn't work.") : (r?.message || `${q.label} done.`)); };
  const busy = runs.some((r) => ["planning", "running"].includes(r.status));
  return (
    <section className="assistant-workspace" aria-label="Assistant">
      <header className="assistant-hero">
        <div className={`assistant-orb${busy ? " is-busy" : ""}${voiceActive ? " is-listening" : ""}`} aria-hidden="true"/>
        <div>
          <h1>Assistant</h1>
          <p>Controls this PC locally with your model. Everyday actions run instantly; anything disruptive asks first.</p>
        </div>
      </header>
      <form className="assistant-command" onSubmit={(e) => { e.preventDefault(); submit(); }}>
        <input ref={input} value={text} onChange={(e) => setText(e.target.value)} aria-label="Tell the assistant what to do"
          placeholder="Tell me what to do — “open Spotify and set volume to 30”"/>
        <button type="button" className={`assistant-mic${voiceActive ? " is-on" : ""}`} aria-pressed={voiceActive} onClick={onToggleVoice}
          title={voiceActive ? "Stop Live Voice" : "Talk to the assistant (Live Voice)"}>{voiceActive ? <Square size={14} strokeWidth={2}/> : <Mic size={17} strokeWidth={1.75}/>}</button>
        <button type="submit" className="assistant-primary" disabled={!text.trim()}>Run</button>
      </form>
      <div className="assistant-quick" role="group" aria-label="Quick controls">
        {QUICK.map((q) => <button key={q.label} className="assistant-tile" onClick={() => quick(q)} title={q.label}><q.Icon size={16} strokeWidth={1.75} aria-hidden="true"/>{q.label}</button>)}
      </div>
      {notice && <p className="assistant-notice" role="status">{notice}</p>}
      <label className="assistant-toggle assistant-setting">
        <input type="checkbox" checked={settings?.autoLowRisk !== false} onChange={(e) => onSettings({ autoLowRisk: e.target.checked })}/>
        Run everyday actions (volume, media, opening apps and folders) without asking
      </label>
      <AssistantCards cards={cards} {...cardHandlers}/>
      {runs.length === 0 ? (
        <div className="assistant-suggestions">
          <p>Try:</p>
          {SUGGESTIONS.map((s) => <button key={s} className="assistant-chip" onClick={() => submit(s)}>{s}</button>)}
        </div>
      ) : (
        <div className="assistant-feed" aria-label="Recent commands" aria-live="polite">
          {runs.map((run) => <RunCard key={run.id} run={run} onDecide={onDecide} onCancel={onCancel} onOpenFile={onOpenFile}/>)}
        </div>
      )}
    </section>
  );
}

export function mergeRun(runs, run) {
  if (!run?.id) return runs;
  const i = runs.findIndex((r) => r.id === run.id);
  if (i < 0) return [run, ...runs].slice(0, 30);
  const next = runs.slice(); next[i] = run; return next;
}
