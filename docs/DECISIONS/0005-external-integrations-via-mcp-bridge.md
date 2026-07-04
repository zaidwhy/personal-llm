# ADR 0005: External integrations (Gmail/Drive) via Claude Code's MCP, not built-in OAuth

**Status:** Accepted

**Context:** v1.0 calls for "1-2 real integrations (Gmail/Drive)". Two paths were considered: (a) a standalone OAuth flow built into `personal_llm` itself - a real Google Cloud project, consent screen, and locally-stored refresh token, so the package can sync on its own schedule independent of any AI assistant session; or (b) treat Claude Code's already-authenticated Gmail/Drive MCP connectors as the fetch layer, and give `personal_llm` a small, credential-free ingestion endpoint that accepts already-fetched content. (a) is meaningfully bigger scope (GCP app registration, scope review, token storage security) for a personal single-user tool; (b) ships today using access that already exists, at the cost of needing a session (or a scheduled script that itself goes through MCP) to trigger a sync rather than a fully unattended cron job.

**Decision:** Path (b). `personal_llm` never talks to Google's APIs and holds no Gmail/Drive credentials. `integrations/schemas.py` defines `ExternalItem` (source, external_id, title, content, url) as the only contract; `integrations/sync.py`'s `sync_external_items()` turns a list of these into normal `ingest_text()` calls, keyed by a `{source}:{external_id}` doc_id so re-running a sync with overlapping items is a no-op for anything already ingested (`MemoryStore.doc_exists()`). The fetch itself - calling Gmail/Drive - happens outside the package: today, that's a Claude Code session using its own MCP tools and writing the result to a JSON file; `cli ingest-external <path>` or `POST /integrations/sync` take it from there. KG extraction is skipped by default for synced items (`extract_kg=False`) since a batch of emails can be numerous and KG extraction costs one LLM call per chunk.

Expected `ExternalItem` JSON shape (placeholder values only - this is a format example, never real content):

```json
[
  {
    "source": "gmail",
    "external_id": "example-thread-id-1",
    "title": "Example email subject line",
    "content": "Example email body text goes here.",
    "url": "https://mail.google.com/mail/u/0/#inbox/example-thread-id-1"
  },
  {
    "source": "drive",
    "external_id": "example-file-id-1",
    "title": "Example Document.docx",
    "content": "Example extracted file content goes here.",
    "url": "https://drive.google.com/file/d/example-file-id-1/view"
  }
]
```

**Security rule (non-negotiable):** real Gmail/Drive content fetched during development or use must never be written into this repository, committed, or pushed - not even temporarily. Any JSON file built from real MCP output goes in the OS scratch/temp directory (outside the repo entirely) or, at minimum, under `data/` (now fully gitignored - see the `.gitignore` fix in this same change, which previously only excluded `data/*.db` and `data/chroma/`, missing `data/workspace/` and any ad hoc file placed directly under `data/`). Before any commit that touches this feature, `git status` must be checked for anything unexpected under `data/` or elsewhere, not just trusted to `.gitignore` silently doing the right thing.

**Consequences:** This ships the real capability - genuine Gmail/Drive content becomes queryable/askable memory - without personal_llm ever holding a Google credential. The limitation is real: nothing syncs unless something (a Claude Code session, or a future script that itself authenticates some other way) actively fetches and posts. If unattended daily sync is wanted later, path (a) remains available and is additive - it would plug into the exact same `sync_external_items()` ingestion contract, just with a different, credentialed fetch layer in front of it.
