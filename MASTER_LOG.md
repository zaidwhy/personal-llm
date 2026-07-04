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

## 2026-07-04 - v0.2 Agent + typed tool layer built and verified

- Built `tools/` (`ToolRegistry` with permission-gated `invoke()`, four built-in tools covering all three tiers: `memory_search`/`read_file` read_only, `remember` read_write, `web_fetch` network with an SSRF guard - resolves hostnames and rejects private/loopback/link-local/reserved targets, refuses to auto-follow redirects) and `agent/` (`Agent` plan-act-reflect loop: structured `AgentStep` JSON each turn via the existing router schema mechanism, denied/invalid tool calls come back as an observation instead of crashing the loop, every step/tool-call/final-answer/max-steps-exceeded is written to the audit log).
- Wired into both interfaces: `cli agent "<goal>" [--allow-network] [--allow-write] [--max-steps N]` and `POST /agent/run`. Default permission set is read-only only - network/write are explicit per-run opt-ins, never global.
- Added `MemoryStore.recent_audit()` (public read of the audit table, same reasoning as the earlier `update_meta` addition - callers never reach into `_connect()` privately).
- 19 new tests (13 tools, 6 agent), all passing, fully mocked router - 54/54 total. Verified for real, not just claimed: real CLI `agent` call and real `POST /agent/run` both fail gracefully (exit 1 / HTTP 503, clean error text, no traceback) with no provider configured - identical honest-degradation behavior to v0.1's `ask`.
- Docs: `docs/DECISIONS/0003-agent-tool-permissions.md` (ADR for the three-tier model), ROADMAP.md and README.md updated to mark v0.2 done.
- Not yet done (v0.3, by design): scheduled/proactive reviews, richer router (paid models, multi-provider verification), per-tool (vs per-tier) permission granularity.

## 2026-07-04 - v0.3 Proactive review + router verification built and verified; fixed a dead CI workflow

- `ModelRouter.complete_with_verification()`: queries every currently-available chat provider (not just the first healthy one), flags disagreement via cosine similarity of the **local embeddings** of each answer (no paid arbiter model, no new dependency - ADR 0004). Refactored the duplicated ollama-health-check/gemini-availability logic in `complete()` into a shared `_provider_available()` helper while adding this.
- `review/weekly.py`: `generate_review()` gathers recent memories + important-but-never-accessed ("forgotten") ones, asks the model for structured highlights/forgotten-items/suggested-actions, stores the review itself as a new episodic memory, logs to audit. Promoted `consolidate.py`'s private `_days_since` to a shared `memory/time_utils.days_since()` instead of duplicating it.
- Wired into both interfaces: `cli review [--days N]` / `POST /review/run`, and `cli ask --verify` / `AskRequest.verify` (extends `Answer` with `disagreement`/`alternate_texts`).
- 12 new tests (5 router verification, 2 rag verify wiring, 5 review), 66/66 total. Verified for real: CLI `review` and `ask --verify` both fail gracefully with clear provider-specific errors (confirmed the verify code path is actually reached, not short-circuited, by ingesting a real matching note first); `POST /review/run` and `POST /ask` (verify:true) both return clean 503s on a freshly started server.
- Caught and fixed a real bug while testing: a stray uvicorn process from v0.2 testing was still holding port 8099 (pkill had missed it on Windows), which silently served 20-minutes-stale code and caused a confusing false 404 on `/review/run` - killed by PID via `taskkill`, then re-verified clean on a fresh port.
- Also fixed a pre-existing bug found last session: `.github/workflows/ci.yml` was scoped to branch `main`, but this repo's default branch has always been `master` - so GitHub Actions had never once run. Fixed and confirmed a real green CI run (`✓ test in 3m11s`, windows-latest/Python 3.12) before starting v0.3 work.
- Docs: `docs/DECISIONS/0004-router-verification.md`, ROADMAP.md and README.md updated to mark v0.3 done.
- Not yet done (v1.0, by design): real integrations (Gmail/Drive via existing MCP), OS-level review scheduling (documented as an option, not auto-installed - would touch global Windows Task Scheduler state), packaging for daily use.
