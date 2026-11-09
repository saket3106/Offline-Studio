# OfflineGPT frontend upgrade — active 28 October 2026

Applies only to this canonical frontend. Do not edit Python, bridge protocols, schemas, production assets or real user data. The owner brief below supersedes the older pure-black palette for SOURCE development. Production remains on its previously approved frontend until separately deployed.

HARD RULES
1. Keep every existing feature, route, keyboard shortcut (e.g. Ctrl+N, Ctrl+K) and backend interface working. Do not change existing backend APIs, IPC/bridge messages, data schemas or stored data. If a UI feature needs backend support, build it behind an adapter with a graceful fallback and record the needed additive backend change in docs/BACKEND_REQUESTS.md. Do not edit backend code.
2. Fully offline: no CDN, remote fonts, analytics or runtime network calls. Bundle fonts, icons and libraries locally. New dependencies must be permissively licensed (MIT/Apache/BSD/ISC), small, maintained and version-pinned. Justify each one in docs/ui-decisions.md and prefer what is already installed. Show third-party licences in an About dialog.
3. Detect the embedded Chromium version (QtWebEngine) and only use CSS/JS features it supports. Configure browserslist/PostCSS to match.
4. Components never call the backend directly. Go through one data-access layer, and create a mock adapter (fixtures: long chats, streaming replies, 1,000+ library images, many models, error cases) so the UI runs in a plain browser for development, tests and screenshots. If you can launch the Qt app in your environment, smoke-test inside it; otherwise say so in your report.
5. Evolve existing code instead of rewriting it for its own sake. Keep diffs reviewable and avoid unrelated refactors.
6. Work on a new branch `ui/overhaul`. Commit after every phase. Never force-push or delete user data.
7. Do not ask me questions unless truly blocked. Make sensible decisions, log them in docs/ui-decisions.md and continue.

DESIGN SYSTEM TARGETS
(Starting values. Verify with a script that every text/background token pair meets 4.5:1, and 3:1 for large text and UI components, then adjust.)
- Dark: base #0E0E10, sidebar #121214, card #17171A, popover/modal #1D1D21, border rgba(255,255,255,.08), text #E8E8EA, secondary #A3A3AB, tertiary #7C7C84 (non-essential text only). No pure #000 or pure #FFF for large areas or body text.
- Light: base #FAFAFA, sidebar #F1F1F3 (clearly separated from the canvas), card #FFFFFF, border rgba(0,0,0,.09), text #1A1A1C, secondary #5C5C64.
- One accent (dark #6C9BFF, light #2563EB) used only for focus rings, selection, links, progress and active indicators. Primary buttons stay inverted monochrome (white on dark, black on light). Success/warning/danger colours only for status, and always with an icon or label.
- Typography: keep the serif for page titles and the hero line; a bundled variable sans (Inter or Geist, Segoe UI fallback) at 14px base for the UI; scale 12/13/14/16/20/28; monospace for code and numbers; minimum text size 12px. Add a UI zoom setting (80-150%).
- 4px spacing grid; radii 6/10/14; elevation through surface lightness plus a 1px border (shadows only on popovers and modals); Lucide-style icons at 1.5px stroke, 16/18/20px (keep the current icon set if it is already consistent).
- Motion: 120-200ms ease-out, opacity/transform only, crossfade on theme change, honour prefers-reduced-motion plus an in-app Reduce motion toggle.
- All tokens as CSS variables in one file. Themes: Dark, Light, Auto (follow Windows), High contrast. Set `color-scheme` per theme so scrollbars and any native control match.
- Shared primitives (Radix-based or equivalent, bundled): Button, IconButton (tooltip required), Input, Textarea, Select, Switch, Checkbox, Slider, Tabs (overflow-safe), Segmented control, Tooltip (with shortcut hint), Popover, DropdownMenu, ContextMenu, Dialog, Drawer, Toast, Skeleton, Progress, Badge, Card, EmptyState, ErrorState, Kbd, ScrollArea, Spinner. Every control has hover, pressed, focus-visible, disabled and loading states. Replace ALL native selects, checkboxes and radios, and all unicode glyph icons (▼ ▶), across the app.
- Add a dev-only route `/__ui-kit` that shows every component in every state in both themes.


## Actual workspace constraint

Canonical Source is not a Git checkout. Do not initialize a new repository or switch to historical GitHub/staging copies to fabricate `ui/overhaul` commits. Local phase commits are BLOCKED until the owner designates or establishes the canonical Git metadata. No remote/GitHub operations are part of this UI task. Keep verified work here and record exact phase state in docs/ui-progress.md.
