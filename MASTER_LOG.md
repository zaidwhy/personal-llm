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

## 2026-07-04 - v1.0 real Gmail/Drive integration slice: built, live-verified with real data, and kept out of git

- `integrations/` module: `ExternalItem` (source/external_id/title/content/url) is the only contract - `personal_llm` holds no Gmail/Drive credentials of its own. `sync_external_items()` ingests idempotently, keyed by `{source}:{external_id}` via a new `MemoryStore.doc_exists()`, so re-running a sync never duplicates. Wired to `cli ingest-external <path>` and `POST /integrations/sync`. Decision and reasoning in ADR 0005 - chose "bridge via Claude Code's already-authenticated MCP" over building a standalone OAuth flow into the package (bigger scope, not needed yet).
- Zaid flagged mid-build: make sure real Gmail/Drive content never gets committed. Audited `.gitignore` and found a real gap - it only excluded `data/*.db` and `data/chroma/`, missing `data/workspace/` (the agent's file sandbox) and any ad hoc file dropped directly under `data/`. Fixed to ignore `data/` entirely (the one legitimate tracked file, `data/samples/about-personal-llm.md`, stays tracked since already-tracked files aren't affected by `.gitignore`).
- Live-verified with real data, not synthetic: used the already-connected Gmail/Drive MCP tools to fetch 2 real Gmail threads and the full text of a real Google Doc, wrote them to a JSON file **in the OS scratch/temp directory only** (never inside the repo), ran the real `ingest-external` CLI command against it, and confirmed via `recall` that the real Drive doc surfaced top-ranked (0.74 similarity) with correct `drive:`/`gmail:` source tagging. Confirmed idempotency by re-running (0 ingested, 3 skipped). Deleted the scratch file with real content immediately after verifying.
- Before committing: `git status --ignored` confirmed `data/personal_llm.db`, `data/chroma/`, `data/workspace/` are all ignored, and `git ls-files | grep -i external|gmail|drive` came back empty - nothing real ever touched the tracked tree. The only integrations-related file committed is the ADR, which contains hand-written placeholder JSON only.
- 5 new tests (idempotency, mixed new/existing, doc_id-per-source, audit logging), 71/71 total.

## 2026-07-04 - v1.0 packaging/polish: installable console script, --version, doctor - v1.0 complete

- `pyproject.toml`: added `[project.scripts] personal-llm = "personal_llm.interfaces.cli:app"` plus readme/authors/license metadata. `pip install -e .` now produces a real `personal-llm.exe` in `venv\Scripts` - verified by running it directly (not `python -m ...`).
- `ModelRouter.provider_status()` (public, reuses `_provider_available`) backs a new `doctor` CLI command: prints version, data paths, per-provider availability, and memory/KG stats in one shot - the "run this first" command for daily use. Also added an eager `--version` flag.
- 4 new tests (provider_status unit test, 3 CLI-level tests via `typer.testing.CliRunner` with a monkeypatched `build_engine` - first tests in the suite that exercise the Typer app object directly rather than calling engine functions), 75/75 total.
- Bumped version 0.1.0 -> 1.0.0 in both `__init__.py` and `pyproject.toml` - this closes out the v1.0 roadmap milestone (real integrations + installable package + daily-use polish, all now done).
- Verified for real: reinstalled the package after the version bump and ran the actual installed `.exe` for both `--version` and `doctor`, confirming it reports 1.0.0, real data paths, honest "not configured" provider status, and real memory counts from earlier sessions.
- Next (per Zaid, 2026-07-04): move into v2 - Voice + Vision. Reclassified from "speculative" to "build now" on his explicit instruction; will use local/free tooling (Whisper-family STT, local TTS, OCR ingestion, Gemini multimodal vision) consistent with the local-first/free-tier-by-default principles, not the heavier speculative items (voice cloning, live multi-speaker, marketplace) - those stay out of scope.

## 2026-07-04 - v2 Voice + Vision built and live-verified with real local models

- `voice/stt.py`: `SpeechToText` wraps `faster-whisper` (CPU, int8), lazy-loaded on first call like `LocalEmbedder`. `voice/tts.py`: `TextToSpeech` wraps `pyttsx3` (OS-native SAPI5 voices), saves to a `.wav` file rather than just playing it, so it's a testable artifact. Both added to the shared `Engine` bootstrap (`engine.stt`/`engine.tts`), same singleton pattern as `router`.
- `vision/ocr.py`: `extract_text_from_image()` via `pytesseract`, wired into `memory/ingest.py`'s `read_file()` so images (`.png/.jpg/.jpeg/.bmp/.tiff/.gif`) are ingestable exactly like PDFs already were. `GeminiProvider.describe_image()` + `ModelRouter.describe_image()` (Gemini-only, Ollama has no vision path) added for image Q&A, same clear-error style as `complete()`.
- Wired into CLI (`transcribe`, `ask-voice [--speak]`, `describe-image`, plus images now "just work" with the existing `ingest` command) and FastAPI (`POST /voice/transcribe`, `/voice/ask`, `/vision/describe`, `/vision/ingest`, all via `UploadFile` + a temp-file bridge, cleaned up after each request).
- Design captured in ADR 0006: this reclassifies plain STT/TTS/OCR/single-image-Q&A from the roadmap's old "v2 speculative" bucket to "built" - they're mature, free, offline-capable tech, not research. Voice cloning, live multi-speaker, and anything beyond single-image Q&A stay explicitly out of scope and still speculative.
- 13 new tests (STT/TTS with mocked `faster_whisper.WhisperModel`/`pyttsx3.init`, OCR with mocked `pytesseract`/`PIL.Image`, `describe_image` delegation/error paths with a fake Gemini provider, `read_file` image dispatch), 88/88 total - none touch a real model, real audio, or a real Tesseract binary, matching the existing zero-network test philosophy.
- Live-verified for real, not just unit-tested: synthesized "The quick brown fox jumps over the lazy dog" to a real `.wav` via `TextToSpeech`, transcribed it back via the real `faster-whisper` "base" model (downloaded fresh on first use), and got back the exact same sentence (plus a trailing period) - a self-contained proof needing no microphone or external audio. Ran the real `ask-voice` CLI command against that file (heard the transcript correctly, then failed gracefully with no chat provider configured, exactly like `ask`). Generated a synthetic text image with PIL and confirmed both failure paths are real and honest: `ingest`/`/vision/ingest` correctly report Tesseract isn't installed on this machine (with install instructions), and `describe-image`/`/vision/describe` correctly report no Gemini key is configured - proving the degradation paths work, since the happy paths for those two specific external dependencies aren't provisioned yet.
- Cleaned up all real-model-generated test artifacts (`data/workspace/test_image.png`, `data/voice/roundtrip_test.wav`) after verifying - `data/` is gitignored anyway but no reason to leave clutter.
