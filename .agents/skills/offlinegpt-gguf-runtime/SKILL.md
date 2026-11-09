---
name: offlinegpt-gguf-runtime
description: Diagnose and optimize OfflineGPT existing local llama.cpp GGUF model inference, context budgeting, token streaming, model management, GPU/RAM guards, and cancellation.
---

# OfflineGPT local inference runtime

## Discover
- Read current runtime, EngineManager, model/projector metadata, cancellation and hardware guard code. Preserve the existing bundled llama.cpp backend and per-model GGUF configuration.
- Distinguish real local inference from canned responses; validate model identity and genuine output on a bounded task.

## Requirements
- Measure current context length and prompt/output tokens rather than forcing 8192 for every model. Budget system/tool tokens, evidence and output headroom on every inference call.
- Preserve GPU/RAM admission and protected data. On 8 GiB VRAM / 16 GiB RAM, prefer measured small improvements to speculative offload or enormous context allocations.
- Implement worker-safe streaming and cooperative cancellation; do not promise sub-100ms stop unless actually measured. Ensure unload/worker lifecycle is validated rather than assuming gc.collect() frees all GPU allocations.
- Keep real model attribution, tool-calling, vision projector compatibility, and multi-model selection intact.

## Verify
- Run affected focused runtime tests and, when needed and resources allow, one real model test with recorded model identity, timings, token usage, cancellation and cleanup.
- Do not download models or weaken RAM thresholds without owner authorization.
