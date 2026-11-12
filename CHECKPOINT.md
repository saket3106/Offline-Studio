# CHECKPOINT — fix/ui-voice-overhaul

## MISSION / CURRENT PHASE
User mission: the app works smartly and professionally like online AI apps and like local personal
assistants (Jarvis/Alexa): very interactive Live Voice, and control of the PC. In-place install authorized.
Phase: speed + polish audit. Route-20261113a installed (exe 79464109…). Data in UserData; Backups keep 2.

## NEXT STEP (exact, executable)
"Summarize our chat in one sentence" pulls 3.2k tokens of memory evidence (5.2 s first token) for a 12-message chat:
answer current-chat summaries from the chat itself. Tool turns (datetime) still rebuild the prompt (2.4k, 3.7 s).
Probe: scratchpad cache_turns.sh (real app, CDP). Git: work on `main`; never delete Source/VCRUNTIME140*.dll / MSVCP140.dll.

## DONE
- Turn 2 keeps the cache (identity without load state; host prompt cache sized by free RAM, 1 GB here) · 20408a0 ·
  VERIFIED-REAL 13a cold start: turn 2 reused 644 tokens, first token ~1000 → 294 ms; turns 3-10 230-390 ms
- Stable history window (start moves every 3 turns) · b70ba67 · VERIFIED-REAL 12d (turns 7-10 first token 634-825 → 250-332 ms
  except the window step 638 ms; replay of 506 real turns: reusable prefix 52% → 66%). 5K/8K prompts → 4K output · f3e2423 · UNIT-TESTED
- Image turns routed by intent (generate/edit/ops/describe/chat; model asked when unsure) · 911f8f6 · VERIFIED-REAL 12c
  (new chat "draw…" → image; "make the apple green" → real edit 25 s; attached image + new prompt → new image; long
  prompt with scale/crop/enhance → new image; chat question → text). 4K edits via 2048 px working copy · 2b70120 · VERIFIED-REAL
- Whisper warm CUDA reuse + CPU threads; warm mic per live session · 2811f4e · VERIFIED-REAL (STT 21 s → 222–366 ms; mic 700 → 256 ms)
- No speaking/thinking flicker; speech via web engine (echo-cancelled) + Qt fallback · 2811f4e · VERIFIED-REAL (10/10 chunks)
- Barge-in by voice · 2811f4e + ac357fa · VERIFIED-REAL (fired 4/5 speaking turns; story interrupted & resumed)
- Barge-in on audio thread (not throttled when hidden) · 3b68cb3 · VERIFIED-REAL visible (38 updates/s); hidden UNTESTED
- PC actions engine · d3ff331 · UNIT-TESTED (29 tests)
- PC actions in chat + voice (cards, spoken yes/no) · ac357fa · VERIFIED-REAL chat (open notepad → confirm → launched 222 ms;
  calculator card waits; gaming-mode preview; question stays chat; email drafted by local model); voice UNIT-TESTED
- Send time only from explicit scheduling words · 7b84aab; "capabilities" no longer injects tool schemas · 65593dd · UNIT-TESTED
- Whisper re-warm after model load, 700 ms endpoint, tolerant exit grammar, GTA/Epic + music, model told capabilities · c564508 · UNIT-TESTED (+REAL: GTA resolves to 'Grand Theft Auto V Enhanced')
- Assistant tab: pc_control tools, agent (rules → detect → model plan), risk tiers, voice yes/no · 3e66ca9, 728b6e0, d5ece58, db7bc96 · VERIFIED-REAL (status 111 ms, screenshot 325 ms, volume ~110 ms, show desktop 179 ms; model plan 1.75 s warm)
- UI polish pass from real-app audit (12 items) · ad6126b · VERIFIED-REAL screenshots offline-studio-fix/after/polish
- Voice/chat commands no longer fall through to chat (misheard timer, model planning fallback) · 14be0d1 · VERIFIED-REAL chat ('Set a timer for one unit' → timer, 104 ms, no chat message); voice UNIT-TESTED
- Declutter + retitle (5 chats, backup offline_gpt-pre-retitle-20261107) · 3c85292, 556e434 · VERIFIED-REAL
- Design layer: single-line composer, Inter (inlined), calm canvas, message rhythm · b6f1b66, 0c34b3a · VERIFIED-REAL
- Library/Image Studio/Settings design pass · 3d2a2d3 · VERIFIED-REAL (chips no clip, 1-line card prompts, dark+light shots)
- Barge-in keeps the interrupting words (PcmCarry: 1.5 s pre-roll + recording until next capture) · 1eb3472, 1495a5d ·
  VERIFIED-REAL via internal virtual mic (qa/vmic_barge_in.mjs): fire 395 ms, carry 1700 ms, full sentence transcribed
- Deep AMOLED black dark palette restored (canvas #000, sidebar #080808) · 344cd44 · VERIFIED-REAL computed colours
- Live Voice VRAM reservation for Whisper (fit-target 512+1400 while voice on) · e185bde, 2118883 · UNIT-TESTED;
  installed Voice-20261107z (cf4d7c1). Real run still CPU: orphaned servers held the GPU (see ledger)
- Helper servers tied to app (kill-on-close job) + startup orphan sweep · 640a485 · VERIFIED-REAL (force-close leaves none)
- Whisper-first Live Voice (GPU Whisper, chat fitted around it; make-room once) · f11b504 · VERIFIED-REAL via virtual mic:
  STT cuda 188-388 ms (was 10-12 s), speech end → answer ~2.3 s, cold + model-preloaded; chat 25 tok/s in voice (35 alone)
- Barge-in reference subtraction (speech RMS as echo reference) · cd2b837 · VERIFIED-REAL vmic: 565/627/604 ms, echo-only never fired
- Hindi/Marathi via Kokoro hf_alpha/hm_omega + hi/mr phonemes · af1ef12 · VERIFIED-REAL round trip hi .984 mr .976
- Web/Hybrid grounding ([Verified Search Context], topic query, Always allow, citation chips) · 4e94a94 · VERIFIED-REAL dev run (no refusal, 7-8 cites)
- Multi-sentence voice exit, no false "ended" claims, exam help, dev dir override · d68a9be · UNIT-TESTED
- AI-overview web answers (keyless web provider, fan-out, parallel reads, 5.2k evidence, intent-keeping queries, MET Norway
  weather, DDG 15-min pause) · 66b6665 · VERIFIED-REAL dev run battery3: weather/IPL/price/best LLMs/LLM overview/CEO/Android
  all grounded + cited, 0 refusals (scratchpad battery3.jsonl)
- Header telemetry + Eject, palette #050505/#0C0C0C, model titles, stopped badge · fd02f96 · VERIFIED-REAL screenshots dark+light
- Installed: Web-20261108 exe f5cbb6ca… · rollback: python -B tools/release_inplace.py rollback --name Web-20261108
  (backup tag pre-Web-20261108, 343 chats). Config research_provider=web, 3 queries / 6 pages.

- Settings auto-save toast, Dark/Light/System segment, Test & Benchmark (37.4 tok/s), Force Unload, composer auto-read +
  mic meter, sandboxed code/artifact pane (Preview/Code/Split) · 016dac8 · VERIFIED-REAL dev run (audio muted internally)
- Image Studio seed lock, negative prompt (CFG>1 only), live Step X/28, before/after · a1ce944 · VERIFIED-REAL (seed 4242 x2,
  steps 1..27/28); before/after UNIT-TESTED (no parented image in library)
- Assistant execution log + confirmation cards + step timings · 975ccf9 · VERIFIED-REAL (gaming mode waited, Skip honoured)
- Installed: UI-20261108 exe 8da6b217… · backup tag pre-UI-20261108 (343 chats, db check ok) ·
  rollback: python -B tools/release_inplace.py rollback --name UI-20261108 (restores Web-20261108)
- Live Voice ends on farewells / "end this mode"; model never asks for a phrase · e7efe96 · VERIFIED-REAL vmic (4 clips, 310-1228 ms)
- Image follow-up edits (img2img 0.72 + source seed/size, no vision load) + projector auto-match · f770d03, 5a38bc8 ·
  VERIFIED-REAL (512 apple → green, composition kept, 2 m 39 s)
- Gmail compose/schedule (no account needed), WhatsApp cards (user presses Send), reminders/alarms as timers · 0afbbe9 ·
  VERIFIED-REAL WhatsApp card + reminder in dev app (nothing sent); Gmail UNIT-TESTED
- Distilled Klein 9B (owner-approved download, sha256 23cadc53…) at 4 steps/CFG 1 · f7e66d4 · VERIFIED-REAL: 512 19 s
  (was 140 s), edit 18 s (159 s), 4K 62 s/60 s (243/218 s). 100% crops: base keeps finer detail; plate text garbled
- Native 2K (1920x1088) for 4K/2K/1080p + Lanczos/unsharp, no ESRGAN below 2.05x · 994ca96 · VERIFIED-REAL 4K 62/63 s, far
  more 100% detail; more steps (8/12) gave no gain (27/40/57 s)
- Detail levels (Settings + Studio, flux_detail_level); Extreme = 6-tile img2img 0.4 · 8c1bd2c/6d89c1e · VERIFIED-REAL in app:
  1080p 68 s, 4K 54 s, Extreme 3 m 54 s
- Release tool trims oldest chain authorities to the gate's 64 · 652ae5e (Detail-20261109 holds 66 → never use it as --prior)
- Smart chat box (composer attach/mic/Live Voice/send; agent_route+routeMessage; Settings → Internet & privacy; redo ±web) · 4da7881..
- Web only when asked (ASK_WEB / pasted link / weather), auto-Agent reset before quick actions + New chat, multi-recipient
  email, no sidebar logo · bccd376, ba59f51, 6382ddf · VERIFIED-REAL web/redo/agent routing in app; email demo pending
- Installed: Route-20261111b exe e92cfc5a… · rollback --name Route-20261111b restores m (then move UserData back into Application). Next: Route-20261112a --prior Route-20261111b. 20261111a = failed dir.
- Cleanup 10 Nov: ~46 GB of old Recovery/backups/logs deleted (receipt keep-closure kept). Script followed junctions and emptied
  Application/whisper + stable-diffusion; restored from official whisper.cpp b5454 cuda-12.4 and sd.cpp master-a3c49b1 cuda12
  zips · VERIFIED-REAL (whisper transcribed; FLUX 1280x720 in app 23 s). Source/logs junction → real dir. Build after cleanup UNTESTED.

## IN PROGRESS
- none

## QUEUE
1. Real-speaker barge-in UNTESTED (rule: internal only); 700 ms endpoint splits sentences.
2. Remaining audit items: Models single primary button; Projects/Knowledge page pass.
3. More tools: window switching, clipboard; email settings page outside the card; WhatsApp auto-send stays off by design.
4. 500-word overshoot; agent single-PDF re-run.

## FINDINGS LEDGER
- in_place_packaging.validate_analysis rejects new frozen deps (PIL.ImageGrab) → use Qt/ctypes; never vite build during a release build (ui/ is sealed).
- Live Voice transcription regressed to CPU after chat model load (secondary_release) → _maybe_rewarm_whisper.
- app.py:4132 — Whisper backend from free VRAM excluded warm proc's own VRAM (fixed: reuse_warm_cuda_whisper).
- voice_runtime.py HybridPlayer — web route via WEB_AUDIO_SINK, 2.5 s watchdog → Qt; speech_output='qt' opt-out.
- app.py view settings — PlaybackRequiresUserGesture=False (page audio context otherwise suspended → Qt fallback).
- qa/aec_probe.js — Qt playback reaches mic at 0.21–0.30 RMS; page playback residual ~0.02.
- bargeIn.js — detector accumulates speech ms (syllable dips reset the old "continuous" rule); worklet levels.
- app.py DesktopBridge._assistant_host — AssistantHost, 15 s outbox timer, DPAPI assistant-mail.dpapi.
- app.py App._voice_assistant — hook before voice_intent_candidate; spoken yes/no answers pending voice card.
- assistant_actions.detect — questions → chat; email needs imperative; send time only via _SCHEDULE.
- router.py:306/637 — wants_agent keyword list (removed "capabilities").
- This PC has no High performance plan; gaming mode will duplicate it on confirm (powercfg -duplicatescheme).
- api.open-meteo.com forecast is robots-disallowed (geocoding allowed); MET Norway allowed. Bundled Python has no tzdata
  → research_network._FIXED_ZONES. DDG Lite human-checks this IP after bursts of test queries.
- Shell heredocs turn \\b into backspace (0x08) in patch scripts: write patches with the Write tool; grep $'\x08' after.
- release_inplace prepare admits NO new root .py modules (sealed hidden imports): put new code in existing modules.

- USER RULE: run tests internally only (no audio through speakers). qa/vmic_barge_in.mjs fakes getUserMedia
  with WAVs and mutes spoken answers. Release builds pack Source/ui: run vite build BEFORE prepare (release v shipped stale ui).
- 12 s STT root causes: (a) orphaned llama/whisper servers held ~5 GB VRAM; (b) model-first load left 0.75-1.25 GB
  even with --fit-target 1912 → Whisper CPU; (c) low-RAM rule unloaded chat mid-turn even when reusing warm Whisper. The venv python.exe redirector kills its children via its own job (test pitfall).
- main.jsx applyLiveSession: after interrupt the backend reports 'thinking' (cancelling) — a fired monitor must survive it.

## PRE-EXISTING FAILURES
test_history_change_polarity (2), test_history_claim_ledger (4), test_transaction_semantics (3),
test_professional_edition (1), test_semantic_acceptance (1). Full run @28a50e9+: 1,633 tests, only test_professional_edition errored.
## CONCURRENCY NOTES
- max 1 subagent used.
