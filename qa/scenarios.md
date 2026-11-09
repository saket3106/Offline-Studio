# Offline Studio — real-app QA scenarios

Drive the installed app, not the mock. Launch with DevTools on loopback:

```powershell
$env:QTWEBENGINE_REMOTE_DEBUGGING='9333'; Start-Process 'C:\Users\mesak\Documents\OfflineGPT\Application\Offline Studio.exe'
node qa/cdp.mjs evalfile qa/send_and_watch.js '{"text":"explain what is a LLM model in 500 words"}'
node qa/cdp.mjs shot ..\offline-studio-fix\after\<name>.png
powershell -File qa\window.ps1 -Out ..\offline-studio-fix\after\<name>-window.png
```

Per-call trace: `Application\logs\turn_trace.jsonl` (one line per model call: turn, purpose, tokens, stop, firstTokenMs, durationMs, prefill/cache when reported).

| # | Scenario | Pass criteria |
|---|---|---|
| 1 | Offline: "explain what is a LLM model in 100 words" | 1 answer call in trace, wipes=0, 75–125 words, no banner |
| 2 | Same chat: "…in 500 words" | 1 call, wipes=0, 375–625 words, ends on a full sentence |
| 3 | Same chat: "now summarize that in 3 bullet points" | uses history, 1 call |
| 4 | Smart Hybrid: "gather all info about LLM models" | research line present, `[n]` links, rawIdsLeft=0 |
| 5 | Voice: three spoken turns incl. interrupt | slim bar states, 1 answer per turn, sensible title (needs a human speaker) |
| 6 | Agent: "find a pdf about self learning in Downloads"; attach one PDF + "summarize this" | finds SELF_LEARNING_*.pdf; summary without "context budget exhausted" |
| 7 | Image Studio: generate 1024×576 | progress in preview, thumbnail + Library entry |
| 8 | Theme dark → light → dark on Chat/Models/Studio/Library/Knowledge | caption follows (window.ps1 immersiveDark/captionColor) |
| 9 | Navigate pages while streaming | stream continues, model state consistent |
| 10 | Restart | chats/settings/theme persist; mic permission not asked again |
