const terminalStates = new Set(["COMPLETED", "ANSWERED", "PARTIAL", "FAILED", "CANCELED", "CANCELLED", "BUDGET_EXHAUSTED", "INTERRUPTED"]);
export const isAgentTerminal = state => terminalStates.has(state);

export function traceOutcome(trace) {
  const status = String(trace?.status || "").toLowerCase();
  if (["error", "failed", "failure", "blocked", "denied"].includes(status)) return "error";
  if (trace?.output?.passed === false || trace?.output?.error) return "error";
  if (["ok", "success", "completed"].includes(status) && trace?.output?.ok !== false && trace?.output?.testResult?.passed !== false) return "success";
  return "unknown";
}

export function executionPreviewValid(preview) {
  const sha = value => typeof value === "string" && /^[a-f\d]{64}$/i.test(value);
  return !!(preview && preview.executionWarning?.includes("NOT A SECURITY SANDBOX") &&
    sha(preview.planSha256) && typeof preview.cwd === "string" && preview.cwd &&
    typeof preview.runtime === "string" && preview.runtime && Array.isArray(preview.command) &&
    preview.command.length > 0 && preview.command.every(item => typeof item === "string" && item) &&
    Number.isFinite(preview.timeoutSeconds) && preview.timeoutSeconds > 0 && preview.timeoutSeconds <= 8 &&
    Array.isArray(preview.files) && preview.files.length > 0 && preview.files.length <= 32 &&
    preview.files.every(file => typeof file.path === "string" && file.path && sha(file.sha256) && Number.isInteger(file.bytes) && file.bytes >= 0));
}
