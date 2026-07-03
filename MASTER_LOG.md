# Personal LLM - Master Log

Append-only. Newest entries at the bottom. Read just the tail for recent context.

## 2026-07-04 - Project created

- Repo scaffolded at `C:\Users\Asus\projects\personal-llm` per the architecture blueprint in `docs/`.
- Building v0.1 "Memory + RAG spine": model router (Gemini + optional Ollama), SQLite memory store, Chroma vector store, ingest/retrieve/RAG pipeline, minimal knowledge graph, CLI/API/Streamlit interfaces, pytest + CI.
- Stack: Python 3.12 venv, Pydantic v2, FastAPI, Chroma, sentence-transformers (local embeddings, zero-cost), SQLite for episodic memory + graph.

## 2026-07-04 - v0.1 Memory + RAG spine built and verified end-to-end

- Full docs written: PRD.md, TDD.md, ARCHITECTURE.md, ROADMAP.md, COMPETITORS.md, 2 ADRs - complete P0-P3 triage of the original brief.
- Built the engine: `router/` (hybrid Gemini+Ollama+local embeddings), `memory/` (SQLite store, ingest, retrieve, consolidate, vectors/Chroma), `graph/kg.py` (LLM triple extraction + NetworkX traversal), `rag/pipeline.py` (grounded answers with citations + honest "not in memory").
- Built 3 interfaces: Typer CLI, FastAPI, Streamlit chat - all sharing one `engine.py` bootstrap.
- 35 pytest tests, all passing, fully mocked (no network/API key needed) - `venv\Scripts\python -m pytest tests/ -q`.
- End-to-end verified for real: created Python 3.12 venv, installed all deps, ingested a real markdown file (local sentence-transformers model auto-downloaded and cached), ran `recall` (correct semantic ranking, 0.44 similarity), ran `stats`, confirmed `ask` fails with a clear 503/error message when no provider is configured (proves offline-capable ingest/retrieve, graceful degradation for generation), verified FastAPI (`/stats` 200, `/ask` 503 with detail) and Streamlit (200, no crash) both serve correctly.
- Not yet done: git init/commit (intentionally left for the user to request), agents/tools (v0.2, by design), real .env with GEMINI_API_KEY (user must supply).

## 2026-07-04 - Squashed initial history, scoped global auto-commit hook

- Squashed the accidental 2-commit history (root commit + an unwanted global-hook auto-commit of README.md) into one clean commit, force-pushed to origin.
- Discovered the global PostToolUse Write|Edit hook in ~/.claude/settings.json was auto-committing every saved file in ANY git repo on the machine, not just the syzayd/syzayd profile repo it was meant for. Scoped it to only fire under projects/syzayd-profile-repo; verified via this exact edit that it no longer auto-commits here.
