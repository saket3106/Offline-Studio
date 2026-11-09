import React, { useEffect, useState } from "react";
import { Rocket, Zap, Mail, MessageCircle, X } from "lucide-react";

// Local assistant action cards: preview → Confirm / Cancel. Nothing runs on this PC until the
// user confirms here or says "yes" in Live Voice. Cards come from bridge.assistantPlan and are
// updated by "assistantAction" events.

const TITLES = { launch: "Open app", power: "Power mode", email: "Email", whatsapp: "WhatsApp" };
const ICONS = { launch: Rocket, power: Zap, email: Mail, whatsapp: MessageCircle };
const toLocalInput = (seconds) => {
  if (!seconds) return "";
  const d = new Date(seconds * 1000); const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
};

export function mergeAssistantCard(cards, card) {
  if (!card?.id) return cards;
  const index = cards.findIndex((c) => c.id === card.id);
  if (index < 0) return [...cards, card].slice(-4);
  const next = cards.slice(); next[index] = { ...cards[index], ...card }; return next;
}

// Email account: connect once (the sign-in is tested before anything is saved), then scheduled
// emails are sent by this app at the chosen time with no Gmail window and no Send click.
export function EmailSetup({ onSave, account, compact = false }) {
  const [email, setEmail] = useState(account?.email || ""); const [password, setPassword] = useState(""); const [name, setName] = useState(account?.name || "");
  const [host, setHost] = useState(""); const [saving, setSaving] = useState(false); const [error, setError] = useState("");
  useEffect(() => { if (account?.email) setEmail(account.email); if (account?.name) setName(account.name); }, [account?.email, account?.name]);
  const connected = !!(account?.email && account?.passwordStored);
  const run = async (data) => {
    setSaving(true); setError("");
    const result = await onSave(data);
    setSaving(false); if (!result?.ok) setError(result?.error || "Could not connect the email account."); else setPassword("");
    return result;
  };
  if (connected) return (
    <div className="assistant-setup email-connected" role="group" aria-label="Email account">
      <p className="email-status"><span className="email-dot" aria-hidden="true"/>Connected as <strong>{account.email}</strong>{account.name ? ` · signs as ${account.name}` : ""}</p>
      <p className="assistant-note">Scheduled emails are sent automatically from this account at the chosen time while Offline Studio is running. No Gmail window, no Send button.</p>
      {!compact && <div className="assistant-actions"><button className="assistant-secondary" disabled={saving} onClick={() => run({ disconnect: true })}>{saving ? "Disconnecting…" : "Disconnect"}</button></div>}
      {error && <p className="assistant-error" role="alert">{error}</p>}
    </div>
  );
  const gmail = /@[^@\s]+\.[a-z]{2,}$/i.test(email.trim()) && !/@(outlook|hotmail|live|yahoo|icloud)\./i.test(email);
  return (
    <div className="assistant-setup" role="group" aria-label="Email account setup">
      <p className="assistant-note">Connect your email once to send and schedule emails automatically. The password is encrypted for this Windows user and only used to sign in to your mail server.</p>
      <div className="assistant-grid">
        <label>Your email<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@gmail.com" autoComplete="off"/></label>
        <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} placeholder="Signs your emails"/></label>
        <label>App password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="16 letters, spaces are fine" autoComplete="new-password"/></label>
        <label>Mail server (optional)<input value={host} onChange={(e) => setHost(e.target.value)} placeholder="Leave empty, found automatically"/></label>
      </div>
      {gmail && <p className="assistant-note">Gmail and Google college/work accounts need an App Password, not your normal password: Google Account → Security → 2-Step Verification → App passwords. Create one named “Offline Studio” and paste it here.</p>}
      {error && <p className="assistant-error" role="alert">{error}</p>}
      <div className="assistant-actions"><button className="assistant-primary" disabled={saving || !email.trim() || !password.trim()} onClick={() => run({ email: email.trim(), password, name: name.trim(), ...(host.trim() ? { smtpHost: host.trim() } : {}) })}>{saving ? "Testing sign-in…" : "Connect & test"}</button></div>
    </div>
  );
}

function AssistantCard({ card, onExecute, onCancel, onDismiss, onSaveEmail }) {
  const [to, setTo] = useState(card.to || ""); const [subject, setSubject] = useState(card.subject || "");
  const [body, setBody] = useState(card.body || ""); const [when, setWhen] = useState(toLocalInput(card.sendAt));
  const [choice, setChoice] = useState(0); const [usePower, setUsePower] = useState(true);
  const [configured, setConfigured] = useState(!!card.configured);
  const [phone, setPhone] = useState(card.phone || ""); const [text, setText] = useState(card.text || "");
  useEffect(() => { if (card.status === "awaiting" && card.kind === "email") { setSubject(card.subject || ""); setBody(card.body || ""); setTo((v) => v || card.to || ""); } }, [card.status, card.subject, card.body]);
  useEffect(() => { if (["done", "cancelled"].includes(card.status)) { const t = setTimeout(() => onDismiss(card.id), card.status === "done" ? 8000 : 2500); return () => clearTimeout(t); } }, [card.status]);
  const awaiting = card.status === "awaiting"; const running = card.status === "running";
  const final = ["done", "scheduled", "cancelled"].includes(card.status);
  const confirm = () => {
    if (card.kind === "email") {
      const sendAt = when ? new Date(when).getTime() / 1000 : null;
      onExecute(card.id, { to, subject, body, sendAt });
    } else if (card.kind === "whatsapp") {
      onExecute(card.id, { to, phone, text, sendAt: when ? new Date(when).getTime() / 1000 : null });
    } else if (card.kind === "launch") onExecute(card.id, { appIndex: choice, power: usePower });
    else onExecute(card.id, {});
  };
  const openGmail = () => onExecute(card.id, { to, subject, body, sendAt: when ? new Date(when).getTime() / 1000 : null, via: "gmail" });
  const apps = card.kind === "launch" && card.app ? [card.app, ...(card.alternatives || [])] : [];
  const scheduled = (card.kind === "email" || card.kind === "whatsapp") && when && new Date(when).getTime() > Date.now() + 30000;
  const verb = card.kind === "whatsapp" ? (scheduled ? "Schedule" : "Open in WhatsApp") : card.kind === "email" ? (scheduled ? "Schedule" : "Send") : card.kind === "launch" ? (card.gaming ? "Play" : "Open") : "Switch";
  return (
    <section className={`assistant-card is-${card.status}`} aria-label={`${TITLES[card.kind] || "Action"}: ${card.summary || ""}`}>
      <header className="assistant-card-head">
        <span className="assistant-icon" aria-hidden="true">{React.createElement(ICONS[card.kind] || Zap, { size: 16, strokeWidth: 1.75 })}</span>
        <div className="assistant-head-text">
          <strong>{TITLES[card.kind] || "Action"}</strong>
          <span className="assistant-summary" role="status" aria-live="polite">{card.status === "drafting" ? "Writing your email with the local model…" : card.summary}</span>
        </div>
        <button className="assistant-close" aria-label="Dismiss" onClick={() => (awaiting || card.status === "drafting" ? onCancel(card.id) : onDismiss(card.id))}><X size={15} strokeWidth={1.75}/></button>
      </header>
      {card.request && <p className="assistant-request">“{card.request}”</p>}
      {card.kind === "launch" && apps.length > 1 && awaiting && (
        <div className="assistant-choices" role="radiogroup" aria-label="Which app">
          {apps.map((app, i) => (
            <label key={app.target} className={i === choice ? "is-selected" : ""}>
              <input type="radio" name={`app-${card.id}`} checked={i === choice} onChange={() => setChoice(i)}/>
              {app.name}<small>{app.source}</small>
            </label>
          ))}
        </div>
      )}
      {card.kind === "launch" && card.power && awaiting && (
        <label className="assistant-toggle"><input type="checkbox" checked={usePower} onChange={(e) => setUsePower(e.target.checked)}/>Gaming mode: {card.power.target?.name} power plan + Windows Game Mode</label>
      )}
      {card.kind === "email" && !final && (
        <div className="assistant-email">
          {!configured && (
            <details className="assistant-email-setup-toggle" open={!!card.sendAt || undefined}>
              <summary>{card.sendAt ? "To send this automatically at the scheduled time, connect your email" : "Send automatically without opening Gmail (connect your account)"}</summary>
              <EmailSetup onSave={async (data) => { const r = await onSaveEmail(data); if (r?.ok) setConfigured(true); return r; }}/>
            </details>
          )}
          <label>To<input type="email" value={to} onChange={(e) => setTo(e.target.value)} placeholder="name@example.com" disabled={!awaiting}/></label>
          <label>Subject<input value={subject} onChange={(e) => setSubject(e.target.value)} disabled={!awaiting}/></label>
          <label>Message<textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} disabled={!awaiting}/></label>
          <label>Send at (optional)<input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} disabled={!awaiting}/></label>
        </div>
      )}
      {card.kind === "whatsapp" && !final && (
        <div className="assistant-email">
          <label>To<input value={to} onChange={(e) => setTo(e.target.value)} placeholder="Name" disabled={!awaiting}/></label>
          <label>Phone (optional)<input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+91 98765 43210, or pick the chat in WhatsApp" disabled={!awaiting}/></label>
          <label>Message<textarea rows={4} value={text} onChange={(e) => setText(e.target.value)} disabled={!awaiting}/></label>
          <label>Send at (optional)<input type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} disabled={!awaiting}/></label>
          <p className="assistant-note">WhatsApp opens with the message typed in. You press Send there.</p>
        </div>
      )}
      {card.error && !final && <p className="assistant-error" role="alert">{card.error}</p>}
      {(awaiting || running || card.status === "drafting") && (
        <div className="assistant-actions">
          {card.kind === "email" && !configured
            ? <button className="assistant-primary" disabled={!awaiting || !body} onClick={openGmail}>{running ? "Working…" : scheduled ? "Schedule in Gmail" : "Open in Gmail"}</button>
            : <button className="assistant-primary" disabled={!awaiting || (card.kind === "email" && (!to || !body)) || (card.kind === "whatsapp" && !text.trim())} onClick={confirm}>{running ? "Working…" : verb}</button>}
          {card.kind === "email" && configured && <button className="assistant-secondary" disabled={!awaiting || !body} onClick={openGmail}>Open in Gmail</button>}
          <button className="assistant-secondary" disabled={running} onClick={() => onCancel(card.id)}>Cancel</button>
          {card.source === "voice" && awaiting && <span className="assistant-hint">or say “yes”</span>}
        </div>
      )}
    </section>
  );
}

// Background progress (writing, scheduled, sending, done) shows as a small toast at the top right;
// only cards that need the user (review, missing address) stay in the chat.
export const isToast = (card) => ["running", "scheduled", "done", "cancelled"].includes(card.status) || (card.status === "drafting" && !!card.sendAt);

function Toast({ card, onCancel, onDismiss }) {
  const Icon = ICONS[card.kind] || Mail;
  useEffect(() => {
    if (card.status !== "done" && card.status !== "cancelled") return undefined;
    const timer = setTimeout(() => onDismiss(card.id), 5000); return () => clearTimeout(timer);
  }, [card.status, card.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const title = card.status === "drafting" ? "Writing email…" : card.status === "running" ? "Working…"
    : card.status === "scheduled" ? (card.kind === "email" ? "Email scheduled" : "Scheduled") : card.status === "cancelled" ? "Cancelled" : card.kind === "email" ? "Email sent" : "Done";
  const when = card.sendAt ? new Date(card.sendAt * 1000).toLocaleString([], { weekday: "short", hour: "numeric", minute: "2-digit" }) : "";
  const line = card.status === "scheduled" && card.kind === "email" ? `To ${card.to}${when ? ` · ${when}` : ""}` : (card.summary || card.to || "");
  return (
    <div className={`assistant-toast is-${card.status}`} role="status">
      <span className="assistant-toast-icon" aria-hidden="true">{card.status === "drafting" || card.status === "running" ? <span className="assistant-toast-spin"/> : <Icon size={15}/>}</span>
      <div className="assistant-toast-text"><strong>{title}</strong><small title={line}>{line}</small></div>
      {card.status === "scheduled" && <button className="assistant-toast-action" onClick={() => onCancel(card.id)}>Undo</button>}
      <button className="assistant-toast-close" aria-label="Dismiss" onClick={() => onDismiss(card.id)}><X size={13}/></button>
    </div>
  );
}

export function AssistantCards({ cards, onExecute, onCancel, onDismiss, onSaveEmail }) {
  if (!cards?.length) return null;
  const toasts = cards.filter(isToast), inline = cards.filter((c) => !isToast(c));
  return (
    <>
      {toasts.length > 0 && <div className="assistant-toasts" aria-live="polite">{toasts.map((card) => <Toast key={card.id} card={card} onCancel={onCancel} onDismiss={onDismiss}/>)}</div>}
      {inline.length > 0 && <div className="assistant-cards" aria-label="Assistant actions">
        {inline.map((card) => <AssistantCard key={card.id} card={card} onExecute={onExecute} onCancel={onCancel} onDismiss={onDismiss} onSaveEmail={onSaveEmail}/>)}
      </div>}
    </>
  );
}
