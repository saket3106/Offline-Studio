# Fix pass ledger — fix/ui-voice-overhaul

Proof is a test name, file, or mock check. "Fixed" = fixed in source and tested there. **Not yet installed** in Application (needs the gated build).

| # | Issue | Status | Proof |
|---|---|---|---|
| 1.0 | One send → answer rewritten 4× | fixed (source) | Cause: validation retry loop (max_retries 2–3) + `partial('')` clear + "in 500 words" parsed as exact. tests/test_one_answer_per_message.py (one call, no clear) |
| 1.0 | Qwen thinking eats budget | not reproducible | GGUF template thinking branch detected; enable_thinking=False except Deep mode (inspected Qwen3.5-9B) |
| 1.1 | Cut mid-sentence + banner | fixed (source) | Budget from requested words (`length_target_output_tokens`), trim to last sentence, footnote + Continue; test_tool_workflow length tests |
| 1.2 | Slow TTFT | partial | cache_prompt already on; Offline voice skips research; no native benchmark run (RAM ~2 GB) |
| 1.3 | Model state mismatch | fixed (source) | `_unload_chat` listeners → modelHealth push; Models page subscribes; test_model_manager_lifecycle OK |
| 1.4 | Research leaks / error as answer | fixed (source) | ResearchPanel only when research ran; failure → local answer + notice; low-RAM lexical fallback |
| 1.5 | Raw citation IDs | fixed (source) | `linkCitations` + uiLogic.test.js; mock check shows [1] [2] links |
| 1.6 | Agent can't find SELF_LEARNING pdf | fixed (source) | `filename_matches` + PDF/DOCX text; tests/test_agent_file_search.py |
| 1.6 | Context budget on one PDF | fixed (source) | `tighten_observation_payloads`; tests/test_recording_regressions.py |
| 1.6 | Agent desk tabs/wrapping | fixed | polish.css; installed 2026-11-06 build |
| 1.7 | Image Studio empty previews | fixed (source) | thumbnails for strip/preview, Generate button; mock check |
| 2 | Voice giant card | fixed (source) | VoiceBar in composer; VoiceSession.vitest.jsx; mock check |
| 2 | Mic permission every start | fixed (source) | permission remembered in config for app origin |
| 2 | Duplicate voice answers | fixed (source) | root cause = 1.0 loops; claim_submission guard already present |
| 2 | Junk titles from transcripts | fixed (source) | `answer_title`; tests/test_voice_titles_and_state.py |
| 2 | Streaming TTS / barge-in latency | open | not changed; needs native mic testing |
| 3 | Composer stacking | fixed (source) | ModeChip in toolbar; IntelligenceBar removed from chat |
| 3 | Caret / actions / jump pill / width | fixed (source) | studio.css |
| 4 | Tokens, one font, dev strings | fixed (source) | studio.css; `.dev-only` |
| 4 | Light title bar dark | fixed (source) | `apply_windows_titlebar_theme` (DWM 20/35/36) — native check pending |
| 5 | Library dup count, Models labels, Knowledge plain status | fixed (source) | main.jsx / models.jsx / Intelligence.jsx |
| 5 | Settings dirty state | fixed | installed 2026-11-06 build |
| 5 | Native folder picker, rename by double-click, bulk bar | open | |
| 6 | Native QA scenarios, after/ screenshots, RESULTS.md | open | |

Test status: backend 1,468 unit tests; only pre-existing failures remain (history_claim_ledger, history_change_polarity, transaction_semantics, professional_edition, semantic_acceptance — identical on snapshot aa6fd9c). Frontend: node 17/17, vitest 19/19, vite build OK.

## 2026-11-07 session
See RESULTS.md for per-issue status, verification level (REAL / MOCK / UNIT / UNTESTED) and evidence in ../offline-studio-fix/after/. Open: 500-word overshoot (~30%), live-voice turns and barge-in (need a human speaker), single-PDF agent summary re-run, Whisper/Kokoro idle preload. Installed: VoiceOverhaul-20261107e (exe 5dca9771...).
