import React, { useEffect, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { FolderOpen, ShieldCheck, Square, CheckCircle2, AlertCircle, Clock, ChevronDown, ChevronRight, Server, Cpu, FileText, Database, HardDrive, Terminal, X } from "lucide-react";

import { isAgentTerminal, traceOutcome, executionPreviewValid } from "./agentLogic.js";
export function agentPhase(state) {
  if (!state || state === "IDLE") return "Ready";
  if (["PREPARING", "RUNNING_MODEL", "REPAIRING_FORMAT"].includes(state)) return "Planning";
  if (state === "AWAITING_APPROVAL") return "Needs permission";
  if (["REQUESTING_TOOL", "EXECUTING_TOOL", "SPECIALIST"].includes(state)) return "Using tools";
  if (["PROCESSING_RESULT", "VERIFYING", "VALIDATING"].includes(state)) return "Reviewing results";
  return ({COMPLETED:"Completed", ANSWERED:"Answered", PARTIAL:"Partial", FAILED:"Failed", CANCELED:"Canceled", INTERRUPTED:"Interrupted", BUDGET_EXHAUSTED:"Limit reached"})[state] || "Working";
}

export function MCPServersManagerPanel({ bridge, onClose }) {
  const [servers, setServers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedServer, setExpandedServer] = useState(null);
  const [error, setError] = useState("");
  const [toggling, setToggling] = useState("");

  const loadServers = async () => {
    setLoading(true);
    setError("");
    try {
      if (bridge?.getMCPServers) {
        const raw = await bridge.getMCPServers();
        const data = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (!data?.ok || !Array.isArray(data.servers)) throw new Error(data?.error || "MCP settings could not be read.");
        if (data?.ok && Array.isArray(data.servers)) {
          setServers(data.servers);
          if (data.servers.length > 0 && !expandedServer) {
            setExpandedServer(data.servers[0].server.name);
          }
        }
      } else throw new Error("The desktop MCP connection is unavailable.");
    } catch (err) {
      setError(err?.message || "MCP settings could not be read.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadServers();
  }, [bridge]);

  const toggleTool = async (toolName, currentEnabled) => {
    if (toggling) return;
    setToggling(toolName); setError("");
    try {
      if (bridge?.toggleMCPTool) {
        const raw = await bridge.toggleMCPTool(toolName, !currentEnabled);
        const result = typeof raw === "string" ? JSON.parse(raw) : raw;
        if (!result?.ok) throw new Error(result?.error || "MCP permission was not changed.");
        await loadServers();
      } else throw new Error("The desktop MCP connection is unavailable.");
    } catch (err) {
      setError(err?.message || "MCP permission was not changed.");
    } finally { setToggling(""); }
  };

  const getServerIcon = (name) => {
    if (name.includes("file")) return <HardDrive size={15} />;
    if (name.includes("document") || name.includes("rag")) return <FileText size={15} />;
    if (name.includes("shell") || name.includes("system")) return <Terminal size={15} />;
    if (name.includes("memory")) return <Database size={15} />;
    return <Server size={15} />;
  };

  return (
    <div className="mcp-manager-container" aria-label="Model Context Protocol (MCP) Manager">
      <div className="mcp-manager-header">
        <div className="mcp-title-wrap">
          <Server size={18} className="mcp-primary-icon" />
          <div>
            <h3>Model Context Protocol (MCP) Manager</h3>
            <p className="mcp-subtitle">Inspect connected local MCP servers, configure tool permissions, and observe runtime capabilities.</p>
          </div>
        </div>
        {onClose && (
          <button type="button" className="mcp-close-btn" onClick={onClose}>
            Close
          </button>
        )}
      </div>

      {error && <p className="agent-error" role="alert">{error} <button type="button" onClick={loadServers}>Retry</button></p>}
      <p className="workspace-note">Permissions apply to this application session. Changes are blocked while a task is running.</p>
      {loading ? (
        <div className="mcp-loading-state">Loading registered MCP servers...</div>
      ) : (
        <div className="mcp-servers-grid">
          {servers.map(({ server, tools }) => {
            const isExpanded = expandedServer === server.name;
            const activeCount = tools.filter(t => t.enabled).length;
            return (
              <div key={server.name} className={"mcp-server-card " + (isExpanded ? "expanded" : "")}>
                <button type="button" className="mcp-server-card-header" aria-expanded={isExpanded} onClick={() => setExpandedServer(isExpanded ? null : server.name)}>
                  <div className="mcp-server-info">
                    <span className="mcp-server-icon">{getServerIcon(server.name)}</span>
                    <div>
                      <span className="mcp-server-name">{server.name}</span>
                      <span className="mcp-server-badge">{server.kind}</span>
                    </div>
                  </div>
                  <div className="mcp-server-meta">
                    <span className="mcp-tool-count-badge">
                      {activeCount}/{tools.length} tools active
                    </span>
                    {isExpanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                  </div>
                </button>

                <p className="mcp-server-desc">{server.description}</p>

                {isExpanded && (
                  <div className="mcp-tools-list">
                    <h4>Available Tools</h4>
                    <div className="mcp-tools-table">
                      {tools.map(tool => (
                        <div key={tool.name} className={"mcp-tool-row " + (tool.enabled ? "enabled" : "disabled")}>
                          <div className="mcp-tool-details">
                            <span className="mcp-tool-name">{tool.name}</span>
                            {tool.is_write && <span className="mcp-perm-badge write">Approval required</span>}
                            {tool.is_host && <span className="mcp-perm-badge host">Host specialist</span>}
                          </div>
                          <label className="mcp-toggle-switch">
                            <input
                              type="checkbox"
                              aria-label={`Enable ${tool.name}`}
                              disabled={!!toggling || loading}
                              checked={tool.enabled}
                              onChange={() => toggleTool(tool.name, tool.enabled)}
                            />
                            <span className="mcp-toggle-slider" />
                          </label>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AgentExecutionTraceView({ traces = [] }) {
  const [openIndices, setOpenIndices] = useState({});

  if (!traces || traces.length === 0) return null;

  const toggle = (idx) => {
    setOpenIndices(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <details className="agent-trace-container" aria-label="Agentic Execution Trace">
      <summary className="agent-trace-header">
        <Cpu size={14} />
        <span>Execution details ({traces.length} tool step{traces.length > 1 ? "s" : ""})</span>
      </summary>
      <div className="agent-trace-steps">
        {traces.map((trace, idx) => {
          const isOpen = !!openIndices[idx];
          const outcome = traceOutcome(trace);
          return (
            <div key={idx} className={"agent-trace-step " + `trace-${outcome}`}>
              <button type="button" className="trace-step-summary" aria-expanded={isOpen} onClick={() => toggle(idx)}>
                <div className="trace-step-left">
                  {outcome === "error" ? (
                    <AlertCircle size={14} className="trace-status-icon error" />
                  ) : outcome === "success" ? (
                    <CheckCircle2 size={14} className="trace-status-icon success" />
                  ) : <Clock size={14} className="trace-status-icon" />}
                  <span className="sr-only">{outcome === "success" ? "Succeeded" : outcome === "error" ? "Failed or blocked" : "Not confirmed successful"}</span>
                  <span className="trace-server-tag">{trace.mcp_server || "mcp"}</span>
                  <span className="trace-tool-tag">{trace.tool}</span>
                </div>
                <div className="trace-step-right">
                  {trace.duration_ms != null && (
                    <span className="trace-duration">
                      <Clock size={11} />
                      {trace.duration_ms}ms
                    </span>
                  )}
                  {isOpen ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                </div>
              </button>

              {isOpen && (
                <div className="trace-step-details">
                  {trace.input_args && Object.keys(trace.input_args).length > 0 && (
                    <div className="trace-payload-section">
                      <span className="trace-section-title">Arguments</span>
                      <pre className="trace-json-payload">{JSON.stringify(trace.input_args, null, 2)}</pre>
                    </div>
                  )}
                  <div className="trace-payload-section">
                    <span className="trace-section-title">Observation Output</span>
                    <pre className="trace-json-payload">
                      {typeof trace.output === "object" ? JSON.stringify(trace.output, null, 2) : String(trace.output || "")}
                    </pre>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </details>
  );
}

export function AgentWorkspacePanel({ bridge, chatId, info, onInfo, request, error, onAttach, onOpenMcpManager, onDisable }) {
  const [events, setEvents] = useState([]);
  const [approval, setApproval] = useState(null);
  const [history, setHistory] = useState([]);
  const [artifacts, setArtifacts] = useState([]);
  const [inspection, setInspection] = useState(null);
  const [feedback, setFeedback] = useState("");
  const [deciding, setDeciding] = useState(false);
  const [workspacePath, setWorkspacePath] = useState("");
  const [previews, setPreviews] = useState([]);
  const [attachmentPath, setAttachmentPath] = useState("");
  const [liveTraces, setLiveTraces] = useState([]);
  const latest = events[events.length - 1];
  const [selectedWorkspace, setSelectedWorkspace] = useState("");
  const [authorizing, setAuthorizing] = useState(false);
  const phase = agentPhase(latest?.state);
  const approvalGeneration = useRef(0);
  const decisionToken = useRef(null);
  const [trustedExecution, setTrustedExecution] = useState(false);
  const [approvalNow, setApprovalNow] = useState(Date.now());
  const isExecution = approval?.tool === "run_python_tests";
  const expired = !!approval?.expiresAt && approvalNow >= approval.expiresAt;
  useEffect(() => {
    setTrustedExecution(false); setApprovalNow(Date.now());
    if (!approval?.expiresAt) return;
    const timer = setInterval(() => setApprovalNow(Date.now()), 500);
    return () => clearInterval(timer);
  }, [approval?.requestId]);

  useEffect(() => {
    let alive = true;
    approvalGeneration.current++; decisionToken.current = null; setDeciding(false);
    setEvents([]); setHistory([]); setApproval(null); setSelectedWorkspace(""); setFeedback(""); setArtifacts([]); setInspection(null); setPreviews([]); setLiveTraces([]);
    request("getAgentHistory").then(result => { if (alive && Array.isArray(result)) setHistory(result); });
    const updateArtifacts = result => {
      if (!alive) return;
      if (Array.isArray(result)) setArtifacts(result);
      else if (result?.error) setFeedback(result.error);
    };
    request("getAgentArtifacts").then(updateArtifacts);
    const onEvent = raw => {
      let event; try { event = JSON.parse(raw); } catch { return; }
      if (!alive || event.type !== "agentStatus" || (event.chatId && event.chatId !== chatId)) return;
      setEvents(previous => [...previous.filter(item => item.taskId === event.taskId), event].slice(-32));
      if (Array.isArray(event.previews)) setPreviews(event.previews);
      if (Array.isArray(event.traces)) setLiveTraces(event.traces);
      approvalGeneration.current++;
      setApproval(event.state === "AWAITING_APPROVAL" ? { ...event.approval, taskId: event.taskId,
        expiresAt: Date.now() + Math.max(0, Number(event.approval?.expiresInSeconds) || 0) * 1000 } : null);
      if (isAgentTerminal(event.state)) {
        request("getAgentStatus").then(result => { if (alive) onInfo(result); });
        request("getAgentHistory").then(result => { if (alive && Array.isArray(result)) setHistory(result); });
        request("getAgentArtifacts").then(updateArtifacts);
      }
    };
    bridge?.event?.connect(onEvent);
    return () => { alive = false; approvalGeneration.current++; decisionToken.current = null; bridge?.event?.disconnect(onEvent); };
  }, [bridge, chatId]);

  const decide = async allow => {
    if (!approval || deciding || (allow && (expired || (isExecution && (!trustedExecution || !executionPreviewValid(approval.preview)))))) return;
    const generation = approvalGeneration.current;
    const token = {}; decisionToken.current = token; setDeciding(true);
    try {
      const result = await request("approveAgent", approval.taskId, approval.requestId, approval.digest, allow);
      if (generation !== approvalGeneration.current) return;
      if (!result?.ok) setFeedback("This approval expired or changed. No operation was authorized.");
      setApproval(null);
    } catch { if (generation === approvalGeneration.current) setFeedback("Approval could not be delivered. The operation remains blocked."); }
    finally { if (decisionToken.current === token) { decisionToken.current = null; setDeciding(false); } }
  };

  return (
    <section className="agent-workspace-panel" aria-label="Local Agent workspace">
      <div className="agent-workspace-heading">
        <strong><ShieldCheck size={15}/> Workspace</strong>
        <span className="agent-phase" data-state={latest?.state || "IDLE"} role="status">{phase}</span>

        <div style={{ display: "flex", gap: "6px" }}>
          <button type="button" className="mcp-manage-btn" onClick={onOpenMcpManager} title="Configure MCP Servers and Tools">
            <Server size={13}/> MCP Tools
          </button>
          <button type="button" disabled={!!info?.active} onClick={async () => {
            const result = await request("pickAgentWorkspace");
            if (result?.ok && result.requiresAuthorization && result.selectedWorkspace) { setSelectedWorkspace(result.selectedWorkspace); setFeedback(""); }
            else if (result?.ok && result.workspace) { onInfo({ ...info, workspace: result.workspace }); setFeedback(""); }
            else if (!result?.cancelled) setFeedback(result?.error || "Workspace selection is unavailable.");
          }}><FolderOpen size={14}/>{info?.workspace ? "Change workspace" : "Choose workspace"}</button>
          <button type="button" className="agent-disable" onClick={onDisable} disabled={!!info?.active} title="Disable Agent Mode" aria-label="Disable Agent Mode"><X size={16}/></button>
        </div>
      </div>
      <div className="agent-scope"><span className="agent-workspace-path" title={info?.workspace || "Only attached files are accessible"}>{info?.workspace || "Attachments only · choose a folder to search files"}</span><span>{info?.toolCounts ? `${info.toolCounts.enabled}/${info.toolCounts.registered} tools enabled` : "Local MCP tools"}</span></div>
      <details className="agent-access-details"><summary>Access & attachments</summary>
      <form className="setting-input-row" onSubmit={async event => {
        event.preventDefault(); setFeedback(""); setSelectedWorkspace(workspacePath.trim());
      }}>
        <label htmlFor="agent-workspace-path">Workspace folder</label>
        <input id="agent-workspace-path" aria-label="Workspace folder" value={workspacePath} disabled={!!info?.active} onChange={event => setWorkspacePath(event.target.value)} placeholder="Paste an exact local folder path"/>
        <button type="submit" disabled={!!info?.active || !workspacePath.trim()}>Authorize this folder</button>
      </form>
      <small>Attached files belong to this conversation. Workspace authorization applies only to the folder you choose and is cleared on restart.</small>
      <details><summary>Attach a file by path</summary><form className="setting-input-row" onSubmit={async event => {
        event.preventDefault();const result=await request("authorizeAgentAttachment",attachmentPath);
        if(result?.ok){onAttach?.(result);setAttachmentPath("");setFeedback("This file is attached to your next message. Its containing folder was not authorized.");}
        else setFeedback(result?.error || "File could not be attached.");
      }}><label htmlFor="agent-attachment-path">Attachment file</label><input id="agent-attachment-path" aria-label="Attachment file" value={attachmentPath} onChange={event=>setAttachmentPath(event.target.value)} disabled={!!info?.active}/><button type="submit" disabled={!!info?.active || !attachmentPath.trim()}>Attach this file</button></form></details>
      {!info?.available && <p role="status">{info?.reason || "Checking local agent dependencies..."}</p>}
      <small>File changes and running reviewed tests require separate, one-use approval. Test execution is not a security sandbox.</small></details>
      {(error || feedback) && <p className="agent-error" role="alert">{error || feedback}{/authoriz|scope|folder/i.test(error || feedback) && <button type="button" disabled={!!info?.active} onClick={async()=>{const result=await request("pickAgentWorkspace");if(result?.selectedWorkspace)setSelectedWorkspace(result.selectedWorkspace);else if(result?.error)setFeedback(result.error);}}>Choose folder access</button>}</p>}
      {latest && <div className="agent-current" role="status"><span>{latest.summary}</span><small>{latest.step || 0}/{latest.maxSteps || 8} steps • {latest.elapsedSeconds || 0}s</small>
        {!isAgentTerminal(latest.state) && <button onClick={() => bridge?.cancelAgent?.()}><Square size={12}/> Cancel</button>}
      </div>}
      {liveTraces.length > 0 && <AgentExecutionTraceView traces={liveTraces} />}
      {events.length > 0 && <details><summary>Task activity</summary><ol>{events.map((event,index) => <li key={index}>{event.summary}{event.failed ? " • failed" : ""}</li>)}</ol></details>}
      {previews.length > 0 && <div aria-label="Visually inspected images">{previews.map(item => <figure key={item.id}>
        <img src={item.thumbnail} alt={`Inspected source: ${item.name}`} width="160" style={{maxHeight:120,objectFit:"contain"}}/>
        <figcaption>{item.name} • Visually inspected</figcaption><button type="button" onClick={() => bridge?.openFile?.(item.path)}>Open original</button>
      </figure>)}</div>}
      {history.length > 0 && <details><summary>Recent agent tasks</summary><ul>{history.map(task => <li key={task.id}>{task.state} • {task.step} steps{task.outcome && <p>{task.outcome}</p>}</li>)}</ul></details>}
      {artifacts.length > 0 && <details className="agent-artifact-journal"><summary>Created files and recovery records ({artifacts.length})</summary>
        <p>Unconfirmed operations may have left a complete, partial or unavailable file. Inspection never retries, deletes or overwrites it.</p>
        <ul>{artifacts.map(item => <li key={item.id}><strong>{item.target}</strong> • {item.state === "VERIFIED" ? "Write acknowledged and verified" : "Interrupted or unconfirmed — review before retrying"}
          <p className="agent-workspace-path">{item.workspace}</p>
          {item.expectedSha256 && <small>Expected SHA-256: {item.expectedSha256}</small>}
          <button type="button" disabled={!!info?.active} onClick={async () => {
            const result = await request("inspectAgentArtifact", item.id);
            if (result?.ok) { setInspection(result); setFeedback(""); }
            else setFeedback(result?.error || "Artifact inspection is unavailable.");
          }}>Inspect without changing files</button>
        </li>)}</ul>
        {inspection && <div role="status"><strong>{inspection.target}: {inspection.inspectionStatus}</strong><p>{inspection.guidance}</p>{inspection.error && <p>{inspection.error}</p>}</div>}
      </details>}
      <Dialog.Root open={!!selectedWorkspace} onOpenChange={open => {if(!open && !authorizing)setSelectedWorkspace("");}}>
        <Dialog.Portal><Dialog.Backdrop className="dialog-overlay"/><Dialog.Popup className="agent-approval-dialog agent-folder-approval">
          <Dialog.Title>Allow access to this folder?</Dialog.Title>
          <Dialog.Description>The Agent may read supported files inside this folder for this application session. Other folders remain private. File changes still require approval.</Dialog.Description>
          <p className="agent-workspace-path">{selectedWorkspace}</p>{feedback && <p role="alert" className="agent-error">{feedback}</p>}
          <div className="agent-approval-actions"><button disabled={authorizing} onClick={()=>setSelectedWorkspace("")}>Cancel</button><button className="primary-button" disabled={authorizing || !!info?.active} onClick={async()=>{
            if(authorizing)return;setAuthorizing(true);
            try {const result=await request("authorizeAgentWorkspace",selectedWorkspace);if(result?.ok){onInfo({...info,workspace:result.workspace});setSelectedWorkspace("");setFeedback("Folder access authorized for this session. File changes still require approval.");}else setFeedback(result?.error || "Folder access was not authorized.");}
            catch {setFeedback("Folder access could not be authorized. Nothing changed.");}finally{setAuthorizing(false);}
          }}>Allow folder access</button></div>
        </Dialog.Popup></Dialog.Portal>
      </Dialog.Root>
      <Dialog.Root open={!!approval} onOpenChange={open => { if (!open) decide(false); }}>
        <Dialog.Portal><Dialog.Backdrop className="dialog-overlay"/><Dialog.Popup className="agent-approval-dialog">
          <Dialog.Title>{isExecution ? "Run these reviewed Python tests?" : "Approve this file operation?"}</Dialog.Title>
          <Dialog.Description>{isExecution ? "Review the exact code identities and execution limits. This runs with your Windows account permissions, not in a security sandbox." : "Review the exact destination and proposed content. Approval applies once to this operation only."}</Dialog.Description>
          <strong>{approval?.tool}</strong><p className="agent-workspace-path">{approval?.preview?.target}</p>
          <p>{approval?.preview?.effects}</p>
          {isExecution ? <>
            <p role="alert">{approval?.preview?.executionWarning || "Execution details are incomplete. Approval is blocked."}</p>
            <dl><dt>Command</dt><dd><code>{approval?.preview?.command?.join(" ")}</code></dd><dt>Working directory</dt><dd>{approval?.preview?.cwd}</dd><dt>Runtime</dt><dd>{approval?.preview?.runtime}</dd><dt>Time limit</dt><dd>{approval?.preview?.timeoutSeconds} seconds</dd><dt>Plan SHA-256</dt><dd><code>{approval?.preview?.planSha256}</code></dd></dl>
            <details><summary>Exact reviewed code ({approval?.preview?.files?.length || 0} files)</summary><pre tabIndex={0}>{JSON.stringify(approval?.preview?.files || [], null, 2)}</pre></details>
            <label><input type="checkbox" checked={trustedExecution} onChange={event => setTrustedExecution(event.target.checked)}/> I trust this reviewed code and understand it runs with my account permissions.</label>
            {!executionPreviewValid(approval?.preview) && <p role="alert">The execution preview is incomplete. Deny or cancel this task.</p>}
          </> : <pre tabIndex={0}>{approval?.preview?.diff ?? approval?.preview?.content ?? (approval?.tool === "create_workspace_directory" ? "Create an empty directory." : JSON.stringify(approval?.preview || {}, null, 2))}</pre>}
          {approval?.expiresAt && <p role="status">{expired ? "This approval has expired. No new operation is authorized." : `Approval expires in ${Math.max(0, Math.ceil((approval.expiresAt - approvalNow) / 1000))} seconds.`}</p>}
          <div className="agent-approval-actions"><button disabled={deciding} onClick={() => bridge?.cancelAgent?.()}>Cancel task</button><button disabled={deciding} onClick={() => decide(false)}>Deny</button><button className="primary-button" disabled={deciding || expired || (isExecution && (!trustedExecution || !executionPreviewValid(approval?.preview)))} onClick={() => decide(true)}>Allow once</button></div>
        </Dialog.Popup></Dialog.Portal>
      </Dialog.Root>
    </section>
  );
}
