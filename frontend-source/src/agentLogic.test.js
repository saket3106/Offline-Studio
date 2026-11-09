import test from "node:test";
import assert from "node:assert/strict";
import {isAgentTerminal, traceOutcome, executionPreviewValid} from "./agentLogic.js";

test("interrupted and canceled tasks are terminal, permission waits are not", () => {
  for (const state of ["INTERRUPTED", "CANCELED", "CANCELLED", "FAILED", "ANSWERED"]) assert.equal(isAgentTerminal(state), true);
  for (const state of ["AWAITING_APPROVAL", "EXECUTING_TOOL", "RUNNING_MODEL", undefined]) assert.equal(isAgentTerminal(state), false);
});
test("missing, canceled and blocked telemetry cannot become successful green steps", () => {
  for (const status of [undefined, "cancelled", "partial", "running"]) assert.equal(traceOutcome({status}), "unknown");
  for (const status of ["error", "failed", "blocked", "denied"]) assert.equal(traceOutcome({status}), "error");
  assert.equal(traceOutcome({status:"success", output:{ok:false}}),"unknown");
  assert.equal(traceOutcome({status:"ok", output:{testResult:{passed:false}}}),"unknown");
  assert.equal(traceOutcome({status:"success",output:{ok:true}}),"success");
  assert.equal(traceOutcome({status:"completed",output:{passed:false,completed:true,testsRun:2}}),"error");
});
test("test approval requires the exact executable code review and honest warning", () => {
  const preview={executionWarning:"NOT A SECURITY SANDBOX. Runs with user permissions.",planSha256:"a".repeat(64),cwd:"ephemeral snapshot",runtime:"packaged worker",command:["runtime","unittest","test_example.py"],timeoutSeconds:8,files:[{path:"test_example.py",sha256:"b".repeat(64),bytes:320}]};
  assert.equal(executionPreviewValid(preview),true);
  for (const field of ["executionWarning","planSha256","cwd","runtime","command","timeoutSeconds","files"]) assert.equal(executionPreviewValid({...preview,[field]:undefined}),false,field);
  assert.equal(executionPreviewValid({...preview,timeoutSeconds:90}),false);
  assert.equal(executionPreviewValid({...preview,files:[{path:"test.py",sha256:"stale",bytes:2}]}),false);
});
