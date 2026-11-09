# OfflineGPT frontend development

Canonical React UI for the existing QtWebEngine desktop application. Embedded target: Chromium 140. No runtime CDN, downloaded font or cloud dependency.

Use Node 24 and pnpm with the checked-in lockfile. Existing Windows installations may retain canonical-path junctions; do not copy node_modules to another application.

```text
pnpm install --frozen-lockfile
pnpm dev:mock
pnpm test
pnpm test:unit
pnpm lint
pnpm format:check
pnpm test:browser
node scripts/contrast.mjs
pnpm build
```

Dev preview: http://127.0.0.1:5173/?mock (add &stress for 5000 chats/images). UI kit: /__ui-kit. These routes are DEV-only, use synthetic data, and never invoke native tools or models. Browser tests use already installed Edge; install a supported test browser explicitly on other machines. They do not download a browser automatically.

Design tokens: src/tokens.css. Existing component styling: styles.css/product.css/refinement.css; behavioral repairs: upgrade.css. Reuse Base UI/Lucide. Native APIs are wrapped unchanged by dataAccess.js. Developer-only dependencies never enter the production bundle.

Real source Qt: use retained SDK Python with ../tests/qt_ui_upgrade.py --out <new isolated evidence path>. At least 2 GiB free RAM; no native models, no real microphone, no production profile. --scale 1.25/1.5/2 --spot verifies process-local Qt scaling without changing Windows settings.

See ../docs/ui-progress.md for the honest phase matrix, ../docs/ui-plan.md, ui-decisions.md and BACKEND_REQUESTS.md. pnpm build writes only ../ui. This is not an installer and does not update Application.
