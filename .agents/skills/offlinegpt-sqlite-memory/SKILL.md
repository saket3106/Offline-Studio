---
name: offlinegpt-sqlite-memory
description: Safely maintain OfflineGPT existing SQLite chat/history storage, memory and RAG retrieval, migrations, WAL, transaction semantics, and preservation of user data.
---

# OfflineGPT SQLite, memory and RAG

## Discover
- Read existing database schema, connection lifecycle, migration strategy, backup policy, retrieval pipeline and tests before proposing change. Do NOT create Argon's replacement SQLiteMemoryStore or an incompatible database.

## Engineering rules
- Preserve existing chat history, media references, model attribution and user profile. Avoid destructive migrations or unrequested retention policy changes.
- Use parameterized SQL, bounded transactions, concurrency-safe connections, WAL where already supported, and correct checkpoint/backup semantics. Do not assume synchronous=NORMAL is right for every durability requirement.
- Keep any schema change backwards compatible or offer a reversible migration; use synthetic database fixtures and verify recovery.
- Improve RAG relevance and citations from genuine retrieved evidence, not fabricated memory.

## Verify
- Run only relevant data/retrieval tests and an isolated synthetic database migration test if schema changed. Never test by overwriting real production SQLite files.
