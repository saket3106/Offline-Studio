---
name: offlinegpt-agent-mcp
description: Improve OfflineGPT genuine offline autonomous Agent Mode, MCP tool calls, workspace boundary checks, approval digests, source patching, test planning, execution evidence, and truthful completion.
---

# OfflineGPT Agent + MCP

## Discover
- Inspect actual agent_runtime.py, agent_permissions, tool adapters, planner, model bridge, and existing acceptance receipts before editing. Never repeat previously solved fixture work without conflicting evidence.

## Safety and behavior
- A tool proposal is not a tool execution. Require real model calls, exact file-specific evidence, current identity, and scoped approval for patches/tests.
- Reject path traversal and symlink/junction escape; never weaken protected Application/Source/Models/Recovery boundaries.
- Fail missing/stale test plans safely, return concise recoverable feedback, and preserve correct approval digest ownership.
- Budget planner context and generation headroom per call; keep runtime evidence on disk while compacting model-facing history.
- Do not claim tests passed without recorded tool output. Use COMPLETED only on required evidence; otherwise honest PARTIAL/FAILED/CANCELLED.
- Track worker ownership, timeout, cancellation and cleanup without falsely treating a cancellation object as exercised behavior.

## Verify
- Run narrow source regressions first. For native acceptance use one bounded genuine installed local model flow if needed and resource-admissible, with approved patch, unchanged tests, plan, execution, result observation, and cleanup.
- Do not modify production data or install the app as an incidental part of a test.
