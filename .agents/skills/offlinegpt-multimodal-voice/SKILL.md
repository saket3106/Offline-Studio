---
name: offlinegpt-multimodal-voice
description: Improve OfflineGPT existing offline vision, image generation/editing, document analysis and Whisper/Kokoro live voice while preserving model provenance, cancellation and accepted behavior.
---

# OfflineGPT multimodal + voice

## Discover
- Inspect current Qwen/vision projector path, FLUX generation/editing, Whisper/Kokoro ASR/TTS pipeline, Qt/React bridge and existing owner-accepted live voice changes.

## Requirements
- Images/screenshot claims require actual image bytes and compatible vision execution; filename-only guesses are not vision.
- Keep FLUX generation/editing provenance, library deduplication, scrolling and file cleanup safe and traceable.
- Voice should handle interruption, streamed model text, TTS audio ownership, bounded response budget and recovery without discarding partial text.
- Keep optional models and backend components load-aware on 8 GiB VRAM / 16 GiB RAM; avoid competing heavyweight loads.
- Preserve user-accepted Live Voice behavior unless actual changed interface requires focused retest.

## Verify
- Do not perform blanket native multimedia tests. Use focused synthetic checks plus one real pipeline check only when resource-safe and relevant, with actual model/ASR/TTS provenance and no fake outputs.
