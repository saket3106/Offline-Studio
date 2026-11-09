import {commandMatches,commandActionKey,usedMemorySources,formatModelName} from "./uiLogic.js";
import {applyLocalDisplay,useUIState} from "./uiState.js";
import {PanelResizeHandle} from "./upgrade.jsx";
import {SelectField} from "./controls.jsx";
import {DETAIL_LEVELS} from "./Intelligence.jsx";
import React, { useState, useEffect, useLayoutEffect, useRef, useMemo } from 'react';
import { Dialog } from '@base-ui/react/dialog';
import { boundedNumber, measuredGiB, recentStudioImages } from './presentation.js';
import { AgentExecutionTraceView } from './agent.jsx';
import { Menu } from '@base-ui/react/menu';
import {
  Lock,
  LockOpen,
  Dices,
  Search,
  X,
  ChevronRight,
  FileText,
  Cpu,
  Mic,
  ShieldCheck,
  PanelRightClose,
  ArrowUpRight,
  SlidersHorizontal,
  MoreHorizontal,
  Sparkles,
  PowerOff,
  Check,
  Image as ImageIcon
} from 'lucide-react';

export function WorkspaceMenu({ label, items, className = "icon-button" }) {
  return (
    <Menu.Root>
      <Menu.Trigger aria-label={label} className={className} title={label}>
        <MoreHorizontal size={18}/>
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner align="end" className="action-menu-positioner" collisionPadding={8} side="bottom" sideOffset={6}>
          <Menu.Popup aria-label={label} className="action-menu-popup">
            {items.map(item => (
              <Menu.Item key={item.id || item.label} data-action={item.id} disabled={item.disabled} onClick={item.run}>
                {item.Icon && <item.Icon size={15} />}
                <span>{item.label}</span>
                {item.hint && <kbd>{item.hint}</kbd>}
              </Menu.Item>
            ))}
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  );
}

export const PresentationContext = React.createContext({
  ui_code_wrap: false,
  ui_message_details: "minimal"
});

export const PRESENTATION_DEFAULTS = {
  theme: 'dark',
  ui_accent: 'neutral',
  ui_density: 'comfortable',
  ui_chat_font_size: 15,
  ui_content_width: 860,
  ui_sidebar: 'expanded',
  ui_inspector: 'contextual',
  ui_motion: 'system',
  ui_message_details: 'minimal',
  ui_code_wrap: false
};

export function applyPresentationToDOM(preferences = PRESENTATION_DEFAULTS) {
  if (typeof document === 'undefined') return;
  const r = document.documentElement;
  const width = boundedNumber(preferences.ui_content_width, 860, 640, 1120);
  const fontSize = boundedNumber(preferences.ui_chat_font_size, 15, 13, 20);
  r.style.setProperty('--content-width', `${width}px`);
  r.style.setProperty('--composer-width', `${width}px`);
  r.style.setProperty('--reading-size', `${fontSize}px`);
  if (preferences.theme === 'light' || preferences.theme === 'dark') {
    r.dataset.theme = preferences.theme;
    try { localStorage.setItem('offline-gpt-theme', preferences.theme); } catch {}
  }
  applyLocalDisplay();
  for (const key of ['accent', 'density', 'motion', 'message_details', 'code_wrap']) {
    const camelKey = key.replace(/_([a-z])/g, (_, v) => v.toUpperCase());
    r.dataset[camelKey] = String(preferences['ui_' + key] ?? PRESENTATION_DEFAULTS['ui_' + key]);
  }
}

export function preferenceRequest(bridge, method, ...args) {
  return new Promise((resolve, reject) => {
    if (!bridge?.[method]) return reject(new Error('Appearance settings require a matching desktop backend.'));
    const timer = setTimeout(() => reject(new Error('Appearance connection timed out.')), 8000);
    try {
      bridge[method](...args, raw => {
        clearTimeout(timer);
        try {
          const result = JSON.parse(raw);
          if (!result.ok) throw new Error(result.error || 'Appearance could not be saved.');
          resolve(result.preferences);
        } catch (e) { reject(e); }
      });
    } catch (e) { clearTimeout(timer); reject(e); }
  });
}

export function usePresentation(bridge) {
  const [preferences, setPreferences] = useState(PRESENTATION_DEFAULTS);
  useEffect(() => {
    let alive = true;
    preferenceRequest(bridge, 'getAppearancePreferences')
      .then(p => { if (alive && p) setPreferences({ ...PRESENTATION_DEFAULTS, ...p }); })
      .catch(() => {});
    const receive = raw => {
      try {
        const e = JSON.parse(raw);
        if (alive && e.type === 'appearancePreferences' && e.preferences) {
          setPreferences({ ...PRESENTATION_DEFAULTS, ...e.preferences });
        }
      } catch {}
    };
    bridge?.event?.connect(receive);
    return () => { alive = false; try { bridge?.event?.disconnect(receive); } catch {} };
  }, [bridge]);

  useEffect(() => { applyPresentationToDOM(preferences); }, [preferences]);
  return preferences;
}

const PREFS = [
  ['theme', 'Color theme', 'A quiet charcoal or bright reading canvas.', [['dark', 'Dark'], ['light', 'Light']]],
  ['ui_accent', 'Accent', 'One quiet accent for selected controls.', [['neutral', 'Blue focus accent']]],
  ['ui_density', 'Interface density', 'Spacing for controls and workspace rows.', [['comfortable', 'Comfortable'], ['compact', 'Compact']]],
  ['ui_sidebar', 'Navigation on startup', 'Your next desktop session starts with this layout.', [['expanded', 'Expanded'], ['collapsed', 'Collapsed']]],
  ['ui_inspector', 'Context behavior', 'Show Agent context automatically or open it yourself.', [['contextual', 'Contextual'], ['manual', 'Manual']]],
  ['ui_motion', 'Motion', 'Reduced motion removes nonessential transitions.', [['system', 'Follow system'], ['reduced', 'Reduced']]],
  ['ui_message_details', 'Response statistics', 'Show token and speed details when the runtime supplies them.', [['minimal', 'Quiet'], ['detailed', 'Detailed']]]
];

export function AppearancePreferences({ bridge, onSaved }) {
  const [draft, setDraft] = useState(PRESENTATION_DEFAULTS);
  const [saved, setSaved] = useState(null);
  const [status, setStatus] = useState('Reading appearance…');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(true);
  const alive = useRef(true);
  const savedRef = useRef(null);

  useEffect(() => {
    alive.current = true;
    setPending(true);
    preferenceRequest(bridge, 'getAppearancePreferences')
      .then(p => {
        if (alive.current && p) {
          const merged = { ...PRESENTATION_DEFAULTS, ...p };
          setDraft(merged); setSaved(merged); savedRef.current = merged; setStatus('Applied preferences');
        }
      })
      .catch(e => alive.current && setError(e.message))
      .finally(() => alive.current && setPending(false));
    return () => { alive.current = false; if (savedRef.current) applyPresentationToDOM(savedRef.current); };
  }, [bridge]);

  const apply = async reset => {
    setPending(true); setError('');
    try {
      const { theme: _theme, ...values } = draft;
      const p = await preferenceRequest(bridge, reset ? 'resetAppearancePreferences' : 'saveAppearancePreferences', ...(reset ? [] : [JSON.stringify(values)]));
      if (alive.current && p) {
        const merged = { ...PRESENTATION_DEFAULTS, ...p };
        setDraft(merged); setSaved(merged); savedRef.current = merged; applyPresentationToDOM(merged); onSaved?.(merged);
        setStatus(reset ? 'Appearance reset.' : 'Saved automatically.');
        if (!reset) showToast('Appearance saved');
      }
    } catch (e) { if (alive.current) setError(e.message); }
    finally { if (alive.current) setPending(false); }
  };

  const update = (k, v) => {
    setDraft(d => {
      const next = { ...d, [k]: v };
      applyPresentationToDOM(next);
      return next;
    });
  };

  const dirty = saved ? JSON.stringify(saved) !== JSON.stringify(draft) : false;
  // Auto-save shortly after the last change (theme has its own control below).
  const applyRef = useRef(apply); applyRef.current = apply;
  useEffect(() => {
    if (!dirty || pending) return;
    const timer = setTimeout(() => applyRef.current(false), 600);
    return () => clearTimeout(timer);
  }, [draft, dirty, pending]);

  return (
    <section className="appearance-workbench" aria-label="Workspace appearance">
      <p className="workspace-note">Changes apply without reloading your model.</p>
      <fieldset disabled={!saved}>
        <div className="preference-grid">
          {PREFS.filter(([key]) => key !== 'theme').map(([key, label, hint, options]) => (
            <label className="preference-field" key={key}>
              <strong>{label}</strong>
              <small>{hint}</small>
              <SelectField aria-label={label} value={draft[key]} onChange={e => update(key, e.target.value)}>
                {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </SelectField>
            </label>
          ))}
        </div>
        <label className="preference-range">
          <span><strong>Chat text size</strong><output>{draft.ui_chat_font_size} px</output></span>
          <input aria-label="Chat text size" type="range" min="13" max="20" step="1" value={draft.ui_chat_font_size} onChange={e => update('ui_chat_font_size', Number(e.target.value))} />
        </label>
        <label className="preference-range">
          <span><strong>Reading width</strong><output>{draft.ui_content_width} px</output></span>
          <input aria-label="Reading width" type="range" min="640" max="1120" step="10" value={draft.ui_content_width} onChange={e => update('ui_content_width', Number(e.target.value))} />
        </label>
        <label className="preference-check">
          <input type="checkbox" checked={!!draft.ui_code_wrap} onChange={e => update('ui_code_wrap', e.target.checked)} />
          <span>Wrap long code lines by default</span>
        </label>
      </fieldset>
      <div className="preference-actions">
        <button type="button" className="secondary-button" disabled={pending || !saved} onClick={() => apply(true)}>Reset appearance</button>
      </div>
      <p role="status" className="workspace-note">{dirty || pending ? 'Saving…' : status || 'Changes save automatically.'}</p>
      {error && <p role="alert" className="settings-feedback is-error">{error}</p>}
    </section>
  );
}

export function CommandPalette({ open, onOpenChange, actions }) {
  const [query, setQuery] = useState('');
  const [index, setIndex] = useState(0);
  const input = useRef(null);
  const list = useRef(null);
  useEffect(()=>{list.current?.querySelector('[data-highlighted="true"]')?.scrollIntoView({block:'nearest'});},[index,query]);
  const results = actions.filter(a => commandMatches(a,query));
  useEffect(()=>setIndex(i=>Math.max(0,Math.min(i,results.length-1))),[results.length]);
  // Reset before paint/focus so the first real keystroke cannot be erased.
  useLayoutEffect(() => { if (open) { setQuery(''); setIndex(0); } }, [open]);
  useEffect(() => setIndex(0), [query]);
  const choose = a => { if (!a) return; onOpenChange(false); a.run(); };
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className="dialog-overlay"/>
        <Dialog.Popup className="command-dialog" initialFocus={input} onKeyDown={e => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { e.preventDefault(); setIndex(i => Math.max(0, Math.min(results.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))); }
          else if (e.key === 'Home' || e.key === 'End') { e.preventDefault(); setIndex(e.key === 'Home' ? 0 : Math.max(0,results.length-1)); }
          else if (e.key === 'Enter' && e.target === input.current && !e.nativeEvent.isComposing) { e.preventDefault(); choose(results[index]); }
        }}>
          <Dialog.Title className="sr-only">Go to a workspace</Dialog.Title>
          <div className="command-search"><Search size={18}/><input ref={input} aria-label="Search commands" placeholder="Where would you like to go?" value={query} onChange={e => setQuery(e.target.value)} /><Dialog.Close aria-label="Close commands" className="icon-button"><X size={16}/></Dialog.Close></div>
          <div className="command-results" ref={list}>{results.map((a, i) => (<button key={commandActionKey(a)} data-highlighted={i === index} className={i === index ? 'command-selected' : ''} onFocus={() => setIndex(i)} onClick={() => choose(a)}><span>{a.label}</span><small>{a.hint || 'Open'} <ArrowUpRight size={13}/></small></button>))}{!results.length && <p>No matching actions.</p>}</div>
          <footer><span>↑ ↓ Navigate · Enter Open</span><kbd>Esc</kbd></footer>
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function ContextInspector({ open, onClose, agentMode, agentPanel, attachments, messages, bridge, modelHealth, onModels, onImages, onVoice, onLiveControl, liveSession, activeView }) {
  const [tab, setTab] = useState(agentMode ? 'agent' : 'sources');
  useEffect(() => { if (agentMode) setTab('agent'); else if (tab === 'agent') setTab('sources'); }, [agentMode]);
  const sources = useMemo(() => {
    const seen = new Set(), found = [];
    for (let i = messages.length - 1; i >= 0 && found.length < 30; i--) {
      for (const source of usedMemorySources(messages[i])) {
        const key = source.chatId + ':' + source.messageId;
        if (!seen.has(key)) { seen.add(key); found.push(source); if (found.length === 30) break; }
      }
    }
    return found.reverse();
  }, [messages]);
  const currentFiles = useMemo(()=>{
    if (attachments.length) return attachments;
    const turn=[...messages].reverse().find(m=>m.role==='user'&&(m.attachments?.length||m.attachment));
    return (turn?.attachments||(turn?.attachment?[turn.attachment]:[])).map(f=>typeof f==='string'?{path:f,name:f.split(/[\\/]/).pop()}:f);
  },[attachments,messages]);
  const traceMessage=[...messages].reverse().find(m=>m.metrics?.agent_traces?.length);
  return (
    <aside hidden={!open} className="context-inspector" aria-label="Workspace context"><PanelResizeHandle/>
      <div className="inspector-heading"><div><h2>{agentMode ? 'Agent desk' : 'Context'}</h2></div><button className="icon-button" aria-label="Close context" onClick={onClose}><PanelRightClose size={18}/></button></div>
      <div className="inspector-tabs" role="group" aria-label="Context views">{[...(agentMode ? [['agent', ShieldCheck, 'Agent']] : []), ['sources', FileText, 'Sources'], ['model', Cpu, 'Model'], ['voice', Mic, 'Voice']].map(([id, Icon, label]) => (<button key={id} aria-pressed={tab === id} onClick={() => setTab(id)}><Icon size={14}/>{label}</button>))}</div>
      <div className="inspector-body">
        <div hidden={tab !== 'agent'}>{agentMode && agentPanel}{agentMode&&traceMessage&&<AgentExecutionTraceView traces={traceMessage.metrics.agent_traces}/>}</div>
        {tab === 'sources' && <><div className="context-section-title"><FileText size={16}/><h3>{attachments.length?'Draft attachments':'Conversation attachments'}</h3><span>{currentFiles.length}</span></div>{!currentFiles.length && <div className="context-empty"><FileText size={28}/><p>Evidence starts here.</p><small>Add a file in the composer.</small></div>}{currentFiles.map((f, i) => (<article className="context-file" key={f.id || f.path || i}><FileText size={18}/><div><strong>{f.name || 'Attachment'}</strong><small>{f.kind || 'Local file'}</small></div></article>))}<h3>Conversation evidence</h3>{sources.length ? sources.map((s, i) => (<button className="context-source" key={i} onClick={() => bridge?.navigateMemorySource?.(s.chatId, s.messageId)}><strong>{s.title}</strong><small>{s.date} · {s.evidenceKind}</small></button>)) : <p className="workspace-note">No conversation evidence attached.</p>}</>}
        {tab === 'model' && <><div className="context-section-title"><Cpu size={16}/><h3>Local inference</h3></div><article className="context-model"><Cpu size={24}/><strong>{modelHealth.modelName || 'See model selector'}</strong><span className="status-pill">{(modelHealth.runtimeLoaded ?? modelHealth.loaded) ? 'Loaded' : 'Not loaded'}</span></article><dl className="context-properties"><dt>Selection</dt><dd>{modelHealth.modelSelectionState || 'See Model Manager'}</dd><dt>Backend</dt><dd>{modelHealth.backend || 'Configured local runtime'}</dd></dl><button className="primary-button" onClick={onModels}>Manage models <ChevronRight size={14}/></button>{activeView === 'studio' && <button className="secondary-button" onClick={onImages}><SlidersHorizontal size={14}/> Image configuration</button>}</>}
        {tab === 'voice' && <div className="context-voice"><div className={'context-orb ' + (liveSession.active ? 'active' : '')}><Mic size={26}/></div><h3>Live Voice</h3><p role="status">{liveSession.active ? liveSession.state : 'Ready when you are.'}</p>{liveSession.active ? <><button className="primary-button" onClick={() => onLiveControl(liveSession.muted ? 'unmute' : 'mute')}>{liveSession.muted ? 'Resume listening' : 'Mute microphone'}</button><button className="secondary-button" onClick={() => onLiveControl('interrupt')}>Interrupt response</button><button className="secondary-button" onClick={() => onLiveControl('exit')}>End voice session</button></> : <button className="primary-button" onClick={onVoice}>Start Live Voice</button>}</div>}
      </div>
      <footer className="inspector-footer"><ShieldCheck size={13}/><span>Local tools · explicit permissions</span></footer>
    </aside>
  );
}

const studioFileUrl = path => /^(file:|data:image\/)/.test(path) ? path : 'file:///' + path.replace(/\\/g, '/').split('/').map((part,i)=>i===0?part:encodeURIComponent(part)).join('/');

// Header telemetry (replaces the bottom status strip): live status while working, context use of the
// latest turn, measured speed and free memory, and Eject. Values appear only when the backend measured them.
export function HeaderTelemetry({modelHealth={},busy,status,elapsedSeconds,messages=[],voiceMode,onResources,onUnload}) {
  const [ejecting,setEjecting]=useState(false),[note,setNote]=useState('');
  const ram=measuredGiB(modelHealth.freeRamBytes),gpu=measuredGiB(modelHealth.freeGpuBytes);
  const loaded=modelHealth.runtimeLoaded ?? modelHealth.loaded;
  const latest=[...messages].reverse().find(m=>m.role==='assistant'&&m.metrics);
  const speed=Number(latest?.metrics?.tokens_per_second);
  const used=Number(latest?.metrics?.prompt_tokens||0)+Number(latest?.metrics?.generated_tokens||0);
  const ctx=Number(modelHealth.effectiveContext||modelHealth.context||0);
  const share=ctx>0&&used>0?Math.min(1,used/ctx):null;
  useEffect(()=>{if(!note)return;const id=setTimeout(()=>setNote(''),4000);return()=>clearTimeout(id)},[note]);
  const eject=async()=>{setEjecting(true);try{await onUnload?.();setNote('Models unloaded')}catch(e){setNote(String(e?.message||e))}finally{setEjecting(false)}};
  return <div className="header-telemetry" role="group" aria-label="Local runtime">
    {busy&&<span className="telemetry-pill is-busy" role="status" title={status}><span className="telemetry-spinner" aria-hidden="true"/>{status||'Working…'}{Number.isFinite(elapsedSeconds)&&elapsedSeconds>0?` · ${elapsedSeconds}s`:''}</span>}
    {!busy&&note&&<span className="telemetry-pill" role="status">{note}</span>}
    {share!==null&&<span className={'telemetry-pill context-meter'+(share>.85?' is-high':'')} title={`Context used by the latest turn: ${used.toLocaleString()} of ${ctx.toLocaleString()} tokens`} aria-label={`Context ${Math.round(share*100)} percent used`}><span className="context-ring" style={{'--share':share}} aria-hidden="true"/>{Math.round(share*100)}%</span>}
    {Number.isFinite(speed)&&speed>0&&<span className="telemetry-pill" title="Generation speed of the latest answer">{speed.toFixed(1)} tok/s</span>}
    {ram&&<button type="button" className="telemetry-pill telemetry-optional" onClick={onResources} title="Free system memory (latest reading)">RAM {ram.replace(' GiB','G')}</button>}
    {gpu&&<button type="button" className="telemetry-pill telemetry-optional" onClick={onResources} title="Free GPU memory (latest reading)">VRAM {gpu.replace(' GiB','G')}</button>}
    {loaded&&<button type="button" className="telemetry-eject" onClick={eject} disabled={ejecting||busy||voiceMode} title={busy?'Stop the answer before unloading':voiceMode?'End Live Voice before unloading':'Unload models and free memory'} aria-label="Unload models"><PowerOff size={15}/></button>}
  </div>;
}

export function RuntimeStatusBar({modelHealth={},busy,status,elapsedSeconds,messages=[],onModels,onResources}) {
  const ram=measuredGiB(modelHealth.freeRamBytes),gpu=measuredGiB(modelHealth.freeGpuBytes);
  const loaded=modelHealth.runtimeLoaded ?? modelHealth.loaded;
  // Show speed only if the backend supplied it, never generate a display estimate.
  const latest=[...messages].reverse().find(m=>m.role==='assistant');
  const speed=latest?.metrics?.tokens_per_second;
  return <footer className="runtime-statusbar" aria-label="Local runtime status"><button onClick={onModels} title="Open Models"><span className="status-dot"/>{formatModelName(modelHealth.runtimeModelName||modelHealth.modelName).name}{loaded?' · loaded':''}</button><span className="status-summary" title={busy?status:'Ready'}>{busy?status:'Ready'}{busy&&Number.isFinite(elapsedSeconds)?` · ${elapsedSeconds}s`:''}</span>{Number.isFinite(speed)&&speed>0&&<span>{speed.toFixed(1)} tok/s</span>}{ram&&<button onClick={onResources} title="Available system RAM; latest backend reading">RAM {ram} free</button>}{gpu&&<button className="gpu-status" onClick={onResources} title="Available GPU memory; latest backend reading">VRAM {gpu} free</button>}<span className="status-private"><ShieldCheck size={12}/>On this computer</span></footer>;
}

/** With a Detail level above Standard the basic presets name only the shape, so the level picks the size. */
export function studioPromptText(format, text, level) {
  const shape = { '1024x576': 'landscape', '768x768': 'square', '576x1024': 'portrait' }[format];
  if (level && level !== 'standard' && shape) return 'Create a ' + shape + ' image of ' + text.trim();
  return 'Create a ' + format + ' image of ' + text.trim();
}

const ASPECT_PRESETS = [
  { label: '16:9 Landscape', value: '1024x576', ratio: '16:9' },
  { label: '1:1 Square', value: '768x768', ratio: '1:1' },
  { label: '9:16 Portrait', value: '576x1024', ratio: '9:16' },
  { label: '21:9 Ultrawide', value: '1280x544', ratio: '21:9' },
  { label: '4K UHD', value: '3840x2160', ratio: 'UHD' },
];

/** Paints a large original (often 3840x2160) at stage size. The image is decoded and
 *  downscaled on the CPU (createImageBitmap) so QtWebEngine never needs a 4K GPU
 *  texture; with the chat model resident, VRAM is tight and such textures fail silently. */
export function StagePreview({ src, alt, ready, onReady, onError }) {
  const canvas = useRef(null);
  useEffect(() => {
    let cancelled = false;
    const img = new Image();
    img.decoding = 'async';
    img.onload = async () => {
      try {
        const host = canvas.current?.parentElement?.getBoundingClientRect();
        const dpr = window.devicePixelRatio || 1;
        const fit = Math.min(1, ((host?.width || 1280) * dpr) / img.naturalWidth, ((host?.height || 720) * dpr) / img.naturalHeight);
        const w = Math.max(1, Math.round(img.naturalWidth * fit)), h = Math.max(1, Math.round(img.naturalHeight * fit));
        const bitmap = await createImageBitmap(img, { resizeWidth: w, resizeHeight: h, resizeQuality: 'high' });
        if (cancelled || !canvas.current) { bitmap.close?.(); return; }
        canvas.current.width = w; canvas.current.height = h;
        canvas.current.getContext('2d').drawImage(bitmap, 0, 0);
        bitmap.close?.(); onReady?.();
      } catch { if (!cancelled) onError?.(); }
    };
    img.onerror = () => { if (!cancelled) onError?.(); };
    img.src = src;
    return () => { cancelled = true; img.onload = img.onerror = null; img.src = ''; };
  }, [src]);
  return <canvas ref={canvas} role="img" aria-label={alt} className={'studio-stage-canvas ' + (ready ? 'is-ready' : 'is-loading')}/>;
}

export function ImageStudio({ onPrompt, onSettings, onLibrary, images=[], busy=false, status='', onPreview, detail=null }) {
  const [text, setText] = useUIState('studioPrompt','');
  const [format, setFormat] = useUIState('studioCanvas','1024x576');
  const [selected, setSelected] = useUIState('studioSelected','');
  const [failed, setFailed] = useState('');
  const recent = useMemo(() => recentStudioImages(images), [images]);
  const image = recent.find(i => (i.path || i.image_path) === selected) || recent[0];
  const path = image?.path || image?.image_path;
  // Library thumbnails load instantly; full-resolution originals (often 4K PNG,
  // 20+ MB) are decoded only for the selected preview, after its thumbnail shows.
  const thumbOf = i => (!i?.thumbnailUnavailable && (i?.thumbnail || i?.thumbnail_path)) || i?.path || i?.image_path;
  const [fullReady, setFullReady] = useState('');
  const [seedLocked, setSeedLocked] = useUIState('studioSeedLock', false);
  const [seed, setSeed] = useUIState('studioSeed', '');
  const [negative, setNegative] = useUIState('studioNegative', '');
  const [compare, setCompare] = useState(false);
  const progress = studioProgress(busy ? status : '');
  // Before/after: an edit, enhancement or upscale is compared with the image it came from.
  const parent = image?.parentId ? images.find(i => i.id === image.parentId && (i.path || i.image_path) && i.fileExists !== false) : null;
  const parentPath = parent?.path || parent?.image_path;
  useEffect(() => { if (!parentPath) setCompare(false); }, [parentPath]);
  const randomSeed = () => String((crypto.getRandomValues(new Uint32Array(1))[0] % 2147483646) + 1);
  const toggleLock = () => { if (!seedLocked && !/^\d+$/.test(String(seed))) setSeed(image?.seed ? String(image.seed) : randomSeed()); setSeedLocked(!seedLocked); };
  return (
    <section className="workspace-view creation-workspace">
      <div className="studio-controls">
        <h1>Image Studio</h1>
        <form
          className="studio-brief"
          onSubmit={e => {
            e.preventDefault();
            if (!busy && text.trim()) onPrompt(studioPromptText(format, text, detail?.level), null, {
              seed: seedLocked && /^\d+$/.test(String(seed)) ? Number(seed) : null,
              negative: negative.trim(),
            });
          }}
        >
          <label htmlFor="studio-description">Your prompt</label>
          <textarea
            id="studio-description"
            aria-label="Studio image description"
            placeholder="Describe the image you have in mind…"
            value={text}
            onChange={e => setText(e.target.value)}
          />

          <div className="studio-aspect-section">
            <span className="studio-aspect-label">Aspect Ratio Presets</span>
            <div className="studio-aspect-chips" role="group" aria-label="Aspect ratio selector">
              {ASPECT_PRESETS.map(preset => (
                <button
                  key={preset.value}
                  type="button"
                  className={`studio-chip ${format === preset.value ? 'is-active' : ''}`}
                  aria-pressed={format === preset.value}
                  onClick={() => setFormat(preset.value)}
                  title={`${preset.label} (${preset.value})`}
                >
                  <span className="studio-chip-ratio">{preset.ratio}</span>
                  <span className="studio-chip-dim">{preset.value}</span>
                </button>
              ))}
            </div>
          </div>

          {detail?.ready && <div className="studio-aspect-section">
            <span className="studio-aspect-label">Detail</span>
            <div className="studio-aspect-chips" role="radiogroup" aria-label="Image detail level">
              {DETAIL_LEVELS.map(([id, name, tip]) => (
                <button key={id} type="button" role="radio" aria-checked={detail.level === id} className={`studio-chip ${detail.level === id ? 'is-active' : ''}`} title={tip} onClick={() => detail.change(id)} disabled={busy}>
                  <span className="studio-chip-ratio">{name}</span>
                  <span className="studio-chip-dim">{tip.split(' · ')[0]}</span>
                </button>
              ))}
            </div>
            {detail.level !== 'standard' && ['1280x544', '3840x2160'].includes(format) === false && <small className="workspace-note">Size comes from the Detail level; the preset sets the shape.</small>}
          </div>}

          <div className="studio-seed-row">
            <span className="studio-aspect-label" id="studio-seed-label">Seed</span>
            <button type="button" className={'studio-seed-lock' + (seedLocked ? ' is-on' : '')} aria-pressed={seedLocked} onClick={toggleLock}
              title={seedLocked ? 'Seed locked: the same seed repeats a composition' : 'Random seed each time; click to lock one'}>
              {seedLocked ? <Lock size={14}/> : <LockOpen size={14}/>}<span>{seedLocked ? 'Locked' : 'Random'}</span>
            </button>
            <input className="studio-seed-input" aria-labelledby="studio-seed-label" inputMode="numeric" disabled={!seedLocked}
              value={seedLocked ? seed : ''} placeholder="Random" onChange={e => setSeed(e.target.value.replace(/\D/g, '').slice(0, 10))}/>
            <button type="button" className="studio-seed-action" disabled={!seedLocked} onClick={() => setSeed(randomSeed())} title="New random seed" aria-label="New random seed"><Dices size={15}/></button>
            {image?.seed !== undefined && image?.seed !== '' && image?.seed !== null && (
              <button type="button" className="studio-seed-action studio-seed-reuse" onClick={() => { setSeed(String(image.seed)); setSeedLocked(true); }} title="Lock the seed of the image shown on the right">Use this image's seed · {image.seed}</button>
            )}
          </div>
          <details className="studio-negative" open={negative ? true : undefined}>
            <summary>Negative prompt{negative.trim() ? <span className="studio-negative-count">on</span> : null}</summary>
            <textarea aria-label="Negative prompt" placeholder="What to keep out, e.g. blurry, text, watermark, extra fingers" value={negative} maxLength={600} onChange={e => setNegative(e.target.value)}/>
            <small className="workspace-note">Used when Guidance (CFG) is above 1 in Generation settings; FLUX at CFG 1 ignores negative prompts.</small>
          </details>
          <div className="studio-submit">
            <button type="submit" className="primary-button studio-generate" disabled={busy || !text.trim()}>
              <Sparkles size={15}/> Generate
            </button>
          </div>
          <small className="workspace-note">Runs on this PC with your local FLUX model. The prompt opens in chat so you can follow progress.</small>
        </form>
        <details className="studio-options">
          <summary>Generation & editing</summary>
          <div className="workspace-toolbar">
            <button type="button" className="secondary-button" onClick={onSettings}>
              <SlidersHorizontal size={15}/> Generation settings
            </button>
            <button type="button" className="secondary-button" onClick={onLibrary}>
              Edit in Library
            </button>
          </div>
        </details>
      </div>

      <div className="studio-preview">
        <div className="studio-stage">
          {busy && /image|flux|generat|diffusion|step|decod|upscal/i.test(status) ? (
            <div className="studio-empty studio-generating" role="status">
              {progress ? <>
                <strong className="studio-step">Step {progress.step}/{progress.total}</strong>
                <div className="studio-progress" role="progressbar" aria-label={progress.label} aria-valuemin={0} aria-valuemax={progress.total} aria-valuenow={progress.step}><span style={{ width: `${Math.round(progress.step / progress.total * 100)}%` }}/></div>
                <p>{progress.label}</p>
              </> : <><span className="studio-spinner" aria-hidden="true"/><p>{status}</p></>}
            </div>
          ) : compare && parentPath && path && failed !== path ? (
            <BeforeAfter before={studioFileUrl(parentPath)} after={studioFileUrl(path)} label={image.operation || 'edit'}/>
          ) : path && failed !== path ? (
            <>
              {fullReady !== path && <img className="studio-stage-thumb" src={studioFileUrl(thumbOf(image))} alt="" aria-hidden="true"/>}
              <StagePreview
                key={path}
                src={studioFileUrl(path)}
                alt={image.displayName || image.prompt || 'Saved local image'}
                ready={fullReady === path}
                onReady={() => setFullReady(path)}
                onError={() => setFailed(path)}
              />
            </>
          ) : (
            <div className="studio-empty">
              <ImageIcon size={28}/>
              <p>
                {path
                  ? 'This preview is unavailable. Open Library to inspect the saved file.'
                  : 'Generated images appear here. Describe an image and press Generate.'}
              </p>
            </div>
          )}
        </div>
        <div className="studio-preview-caption">
          <span>{busy ? status : image?.displayName || image?.prompt || 'Local image workspace'}</span>
          {parentPath && path && !busy && (
            <button type="button" className="secondary-button" aria-pressed={compare} onClick={() => setCompare(v => !v)} title="Compare with the image this one was made from">
              {compare ? 'Hide compare' : 'Before / after'}
            </button>
          )}
          {path && (
            <button
              type="button"
              className="secondary-button"
              onClick={() => onPreview?.(path, image.dimensions)}
            >
              Open preview
            </button>
          )}
        </div>
        <div className="studio-recent" aria-label="Recent saved images">
          {recent.map((i, idx) => {
            const p = i.path || i.image_path;
            return (
              <button
                key={`${p}-${i.id || idx}`}
                type="button"
                title={i.displayName || i.prompt || 'Saved image'}
                aria-label={i.displayName || i.prompt || 'Saved image'}
                aria-pressed={p === path}
                onClick={() => {
                  setSelected(p);
                  setFailed('');
                }}
              >
                <img src={studioFileUrl(thumbOf(i))} alt="" loading="lazy" decoding="async"/>
              </button>
            );
          })}
        </div>
      </div>
    </section>
  );
}

/** "Generating image · step 7 of 28" (from the image engine) → {step, total, label}. */
export function studioProgress(status) {
  const m = String(status || '').match(/^(.*?)\s*·?\s*step\s+(\d+)\s+of\s+(\d+)/i);
  if (!m) return null;
  const step = Number(m[2]), total = Number(m[3]);
  if (!total || step > total) return null;
  return { step, total, label: (m[1] || 'Generating image').replace(/\s*·\s*$/, '').trim() || 'Generating image' };
}
/** Before/after slider: the newer image is revealed from the left up to the handle. Keyboard: arrows / Home / End. */
export function BeforeAfter({ before, after, label = 'edit' }) {
  const [pos, setPos] = useState(50);
  const box = useRef(null);
  const fromPointer = e => { const r = box.current?.getBoundingClientRect(); if (r?.width) setPos(Math.max(0, Math.min(100, ((e.clientX - r.left) / r.width) * 100))); };
  return (
    <div ref={box} className="before-after" onPointerDown={e => { e.currentTarget.setPointerCapture?.(e.pointerId); fromPointer(e); }} onPointerMove={e => { if (e.buttons) fromPointer(e); }}>
      <StagePreview src={before} alt="Before" ready onReady={() => {}} onError={() => {}}/>
      <div className="before-after-top" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
        <StagePreview src={after} alt={`After ${label}`} ready onReady={() => {}} onError={() => {}}/>
      </div>
      <span className="before-after-tag is-before">Before</span><span className="before-after-tag is-after">After</span>
      <input type="range" className="before-after-range" min="0" max="100" step="1" value={Math.round(pos)} aria-label="Before and after comparison"
        aria-valuetext={`${Math.round(pos)}% after`} onChange={e => setPos(Number(e.target.value))}/>
      <span className="before-after-handle" style={{ left: `${pos}%` }} aria-hidden="true"/>
    </div>
  );
}
// Small app-wide toast: showToast('Saved') from anywhere; one host renders it.
export function showToast(text) { window.dispatchEvent(new CustomEvent('studio:toast', { detail: { text: String(text || '') } })); }
export function ToastHost() {
  const [toast, setToast] = useState(null);
  useEffect(() => {
    let timer = 0;
    const onToast = e => { clearTimeout(timer); setToast({ text: e.detail?.text, id: Date.now() }); timer = setTimeout(() => setToast(null), 2400); };
    window.addEventListener('studio:toast', onToast);
    return () => { clearTimeout(timer); window.removeEventListener('studio:toast', onToast); };
  }, []);
  return <div className="toast-host" role="status" aria-live="polite">{toast?.text && <div className="studio-toast" key={toast.id}><Check size={14} aria-hidden="true" />{toast.text}</div>}</div>;
}
