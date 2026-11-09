---
name: offlinegpt-premium-studio-ui
description: Safely refine the existing OfflineGPT Premium Studio React and Qt frontend, chat composer, streaming UI, model picker, theme, image library, and accessibility without replacing architecture.
---

# OfflineGPT Premium Studio UI

Use for frontend UI/UX, React components, styles, Qt WebChannel integration, and desktop interaction flows.

## Discover before editing
- Read repository AGENTS.md and inspect actual frontend paths, components, design tokens, Qt integration and accepted interface. This app is not a greenfield PySide6 QSS-only interface.
- Preserve approved Premium Studio dark and light themes, existing pure-black / near-black direction where selected, existing typography, accessibility, and native bridges. Do not impose the Argon sample slate palette or a generic blue theme.
- Identify one specific UI defect or requested feature and propose a small set of affected files before editing.

## Engineering rules
- Preserve one-line composer that expands for longer messages, attachment/agent/voice/mic/send actions, streaming interaction and stop controls as implemented.
- Ensure auto-scroll respects user manual scroll. Make copy-code and attachment actions real, not decorative.
- Verify state ownership, chat/message ordering, cancellation, image library scrolling/deduplication, model attribution, keyboard support, and color contrast in changed paths.
- Keep UI thread nonblocking; use existing React↔Qt bridge rather than introducing a new frontend stack or parallel app.
- Preserve historical chats, models, settings, and production profile. No mock/canned success badges in actual UI.

## Verify
- Find and run repository's existing focused frontend tests, build/typecheck/lint only when relevant; do not invent commands for files absent from canonical source.
- Compare changed screen or screenshot where possible and verify the actual bridge action behind every newly added control.
- Do not package or install production EXE unless separately authorized.
