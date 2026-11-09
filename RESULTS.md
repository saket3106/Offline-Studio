# Offline Studio fix pass — results (2026-11-07)

Branch `fix/ui-voice-overhaul`. Installed release: see bottom. Real-app checks were driven through the installed
exe's own UI (QtWebEngine DevTools on 127.0.0.1, `qa/cdp.mjs`), real Qwen3.5-9B inference, Windows DWM queries
(`qa/window.ps1`). Labels: **REAL** = verified in the installed app, **MOCK** = verified in the mock UI only,
**UNIT** = automated test only, **UNTESTED**.

## Issues

| # | Issue | Status | Verified | Evidence |
|---|---|---|---|---|
| 1.0 | One send → answer rewritten 4× | fixed | REAL: 100-word (113 w) and 500-word turns each = 1 `answer` call, 0 wipes, stop=`stop` | `turn_trace.jsonl`; after/00_one_answer_500_words.png |
| 1.1 | Cut mid-sentence + banner | fixed | REAL: length stop trimmed to full sentence, "Stopped at the length limit · Continue"; Continue fills composer and continues with history | after/04_length_limit_continue.png |
| 1.1b | Runtime context silently 2048 (Settings shows 4096) | **fixed this session** | REAL: trace `contextLimit` 2048 → 4096 after fix | trace before/after |
| 1.1c | "500 words" overshoot | **open** | REAL: 576, 652, 632, 677 words in four runs (target 375–625); explicit ±10% range in release e did not fix it. Single call, no wipes, full sentences in all runs | trace |
| 1.2 | Slow first token | fixed for chat | REAL: follow-up first text 855–949 ms; prefill 606 ms (392-token prompt); cold model load ≈ 7 s | trace |
| 1.3 | Status bar vs Models page | fixed | REAL: manual unload/load — page, Loaded badge and status bar agree both ways; UNIT: every `_unload_chat` notifies | tests/test_model_state_push.py |
| 1.4 | Research leak / error as answer | fixed | REAL: research line only when research ran; Offline plain turns show none | after/06_citations_research_line.png |
| 1.4b | Web-permission dialog could sit unseen (turn "Worked for 9m 16s") | fixed (release d+) | UNIT: prompt is top-most, named, returns clicked choice | tests/test_permission_prompt.py |
| 1.4c | Smart Hybrid ignored "gather all info / from the internet" | fixed | UNIT routing; REAL research via Web mode | tests/test_permission_prompt.py |
| 1.5 | Raw citation IDs | fixed | REAL: `[1] [2] [3]` links to doi.org / Wikipedia, 0 raw IDs, 0 unrendered links | after/06_citations_research_line.png |
| 1.6 | Agent can't find SELF_LEARNING pdf | fixed | REAL (release d): "Found a PDF about self learning … Self-Learning_Logbook_Alex_Doe_101_TY_IT…" | after/12_agent_finds_self_learning_pdf.png |
| 1.6b | "Agent context budget exhausted" | fixed by 4096 context | REAL: failed at 2048 (release c), succeeded at 4096 (release d). Single attached-PDF summary: UNTESTED this session | — |
| 1.7 | Image Studio empty preview | **fixed this session** | REAL: 4K originals failed to paint under low VRAM; canvas downscale renders (1007×566) | after/08_image_studio_preview.png |
| 2 | Voice card over chat | fixed | REAL: slim bar in 113 ms, Preparing → Starting microphone → Listening (6.5 s), Mute/Unmute/Esc work, no old card | qa/voice_states.js output |
| 2b | Mic permission every start | fixed | REAL: no prompt after restart, config `microphone_permission=granted` | — |
| 2c | Spoken turns: 1 answer, titles, barge-in | UNTESTED (needs a human speaker) | UNIT: one call per voice turn, titling, policy | tests/test_voice_titles_and_state.py |
| 3 | Composer stacking, caret, actions, footnote | fixed | REAL: chips inside toolbar, actions hidden while streaming | after/page_*_*.png |
| 4 | Light title bar stayed dark | fixed | REAL: DWM immersive-dark 1 → 0 → 1 on live toggle; caption pixel #0E0E10 / #FAFAFA; startup dark = 1 | after/03_titlebar_*.png |
| 5 | Library double count | fixed | REAL: one "114 images" | after/page_library_dark.png |
| 5 | Knowledge dev strings | fixed | REAL: "No files indexed yet.", 0 raw codes | after/page_knowledge_*.png |
| 5 | Native folder picker | fixed | UNIT/headless fallback; native dialog itself not driven by automation | agent_desktop.py |
| 5 | Inline rename, bulk-select bar | fixed | UNIT (7 component tests), MOCK visual | sidebarControls.vitest.jsx |
| 3 | Streaming TTS / barge-in < 300 ms | UNTESTED for live speech | REAL read-aloud: first audio 5.7 s cold (Kokoro load), 54 ms warm cached; stop → player gone 44–55 ms | qa/read_aloud_timing.js |

## Measured timings (real app, Qwen3.5-9B Q4_K_M, RTX 4060 8 GB, ~5–6 GiB RAM free)

| Scenario | Result |
|---|---|
| First turn after launch (model cold) | first text 7.6 s (≈7 s load + 682 ms first token) |
| Short follow-up, model resident | first text 855–949 ms; first token 645–809 ms; prefill 606 ms / 392 tokens |
| Long-context turn (1,293-token prompt) | first token 1.57 s, prefill 1.54 s |
| Decode speed | 36–38 tok/s |
| Voice mode start → Listening | 6.5 s (first start; Whisper/Kokoro load) |
| Read aloud first audio | 5.7 s cold / 54 ms cached |
| Stop speech → playback UI gone | 44–55 ms (UI; acoustic stop not measured) |
| Barge-in stop latency (live speech) | not measured — needs a human speaker |

## Tests

Backend: 1,479 tests across all `tests/test_*.py` (one process per file, `tests/run_suite.py`). Only failures: 11 errors in
five files that fail identically on the pre-fix snapshot `aa6fd9c` — `test_history_change_polarity` (2),
`test_history_claim_ledger` (4), `test_transaction_semantics` (3), `test_professional_edition` (1, model placeholder
status), `test_semantic_acceptance` (1, opt-in native acceptance). Frontend: node 17/17, vitest 26/26, vite build OK.

## Known limitations / not done

- Live voice turns, barge-in timing and voice-chat titles need a person speaking; not verified natively.
- Voice first start still loads Whisper/Kokoro (~6 s); preloading at app idle was not added.
- Agent single-PDF summarize was not re-run on release d/e.
- "Task is partial" prefix still appears on the agent file-search answer.
- Next: calibrate the word target sent to the model (e.g. ask for ~0.8× of the requested count) and re-measure 10 runs; preload Whisper/Kokoro at idle; human-run voice turns and barge-in timing; re-run single-PDF agent summary.
- Installed: release VoiceOverhaul-20261107e, exe 5dca97717cac2c78280a1e512f241554e02ec4637775b1071101f71a4e9bcf92 (backups in Application\backups\*pre-VoiceOverhaul-20261107*; rollback: `python -B tools/release_inplace.py rollback --name VoiceOverhaul-20261107e`).
- Release history this session: b (first install), c, d, e — each gated (25 pinned native pairs, 50 signatures, compiled-source acceptance).

## 2026-11-07 (later) — Live Voice + PC actions

| Item | Verified | Evidence |
|---|---|---|
| Transcription on GPU (warm reuse) | VERIFIED-REAL | STT 21,358 ms CPU → 222–366 ms CUDA (stt-profiles) |
| Mic ready after an answer | VERIFIED-REAL | 700 → 256 ms (qa/barge_in_monitor.js timeline) |
| Speech echo-cancelled (played in web engine) | VERIFIED-REAL | 10/10 chunks started, 0 errors; Qt playback hit mic at 0.21–0.30 RMS (qa/aec_probe.js) |
| Barge-in by talking | VERIFIED-REAL | fired 4/5 speaking turns; dragon story interrupted, next turn continued |
| Barge-in while window hidden | UNTESTED (worklet path VERIFIED-REAL visible, 38 updates/s) | qa/worklet_rate_probe.js |
| PC actions: open app | VERIFIED-REAL | "open notepad" → card → Open → launched (222 ms) |
| PC actions: gaming mode preview / question stays chat / email draft | VERIFIED-REAL | qa/assistant_check.js |
| PC actions by voice (spoken yes/no) | UNIT-TESTED | tests/test_assistant_voice_bridge.py |
| Real email send | UNTESTED (needs the user's account) | — |
| Tests | 1,515 backend (only the 5 pre-existing files fail), node 28, vitest 30 | logs/test-runs |

Installed: Assistant-20261107j (exe 0604447d…). Rollback: `python -B tools/release_inplace.py rollback --name Assistant-20261107j`.

## 2026-11-07 (evening) — Assistant tab + UI polish

| Item | Verified | Evidence |
|---|---|---|
| Assistant tab (PC control) | VERIFIED-REAL | status 111 ms, screenshot 325 ms, volume ~110 ms, show desktop 179 ms (qa/assistant_tab_check.js) |
| Model-planned commands | VERIFIED-REAL | 1.75 s warm; tool chosen by local model |
| Voice: Whisper back on GPU after model load | UNIT-TESTED | user's session showed 11 s CPU after turn 2 → fixed c564508 |
| Voice: 'close live voice' misheard variants | UNIT-TESTED | tests/test_live_voice_commands_tolerant.py |
| UI polish (12 audit items) | VERIFIED-REAL screenshots | offline-studio-fix/after/polish, audit in after/audit |

| Design layer (composer, Inter, rhythm) | VERIFIED-REAL screenshots | b6f1b66, 0c34b3a |
| Library/Image Studio/Settings pass | VERIFIED-REAL screenshots | 3d2a2d3; chips clip:false, 1-line prompts, dark+light |

| Barge-in keeps interrupting words | VERIFIED-REAL (virtual mic) | 1495a5d; carry 1700 ms, 'Wait stop the story and tell me...' transcribed in full |
| AMOLED black dark palette | VERIFIED-REAL | 344cd44; main #000, sidebar #080808 |

Installed: Voice-20261107x (exe d61e383d…). Rollback: `python -B tools/release_inplace.py rollback --name Voice-20261107x`.

## 2026-11-07 (night) — Live Voice transcription speed
| Measure (real app, internal virtual mic, nothing played aloud) | Before | After |
|---|---|---|
| Whisper backend in Live Voice | CPU (auto_cpu, 1.0–1.25 GB VRAM free) | CUDA (warm, reused) |
| Transcription per spoken turn | 10.1–11.8 s | 188–388 ms |
| End of speech → spoken answer starts (barge-in turn) | ~15 s + chat reload stall | ~2.3 s |
| Chat speed while voice is on | 35 tok/s | ~25 tok/s (Whisper shares the GPU) |
| Helper servers after force-closing the app | llama + 2 whisper left running (~5 GB VRAM) | none |

Fixes: helper servers in a kill-on-close job + startup orphan sweep (640a485); Whisper loads first and the chat model
is fitted around it, a GPU Whisper stays warm for the whole voice session (f11b504).
Tests: 1567 run, only pre-existing test_professional_edition error. Installed: Voice-20261107b (exe b1c6eba9…).
Rollback: `python -B tools/release_inplace.py rollback --name Voice-20261107b`.
