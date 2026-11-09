---
name: offlinegpt-pyinstaller-release
description: Safely package and release OfflineGPT through its existing approved PyInstaller build, SDK trust pins, signed native inputs, rollback, and one main Windows installation.
---

# OfflineGPT verified packaging and release

## Canonical identity
- Current project root: C:\Users\mesak\Documents\OfflineGPT
- Canonical Source: C:\Users\mesak\Documents\OfflineGPT\Source
- Main EXE: C:\Users\mesak\Documents\OfflineGPT\Application\Offline GPT.exe
- Discover actual verified paths, hashes and latest receipts; never assume historical values are current.

## Build/release rules
- Read and reuse existing spec, manifest, SDK signer/hash pins, build environment and release transactions. Do not substitute a generic `--collect-all` build or a new app layout.
- Signed SDK relocation is permitted ONLY when the exact approved hash, signer, authority and explicit reviewed source→destination mapping are validated. Never silently approve a new signer, weaken gates or trust a normalized PE comparison alone.
- Before any install, verify source inputs, packaging, current EXE/companion rollback scope, and a disposable rollback rehearsal.
- Build at most one current temporary candidate per change; run focused packaged/startup checks; install into the existing main app ONLY when user has authorized that release.
- Preserve normal profile, SQLite, settings, models and UI assets. Never overwrite a running EXE or launch destructive cleanup without ownership checks.
- Verify actual deployed EXE hash and startup. If failed, restore only backed-up application artifacts without reverting newer user data.

## Verify
- Use existing release gate and focused installer/packaging tests. Report source-verified, native-verified, built, installed and owner-tested states separately.
