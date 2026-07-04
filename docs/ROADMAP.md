# Personal LLM - Roadmap

| Phase | Scope | Key deliverables | Success metric |
|---|---|---|---|
| **v0.1 Spine** (done) | Memory + RAG + KG-lite + CLI/API/Streamlit + tests/CI | Model router, SQLite memory store, Chroma ingest/retrieve, grounded RAG with citations, minimal KG, 3 interfaces | Ingest real notes; ask questions; get cited answers; offline-capable for ingest/retrieve |
| **v0.2 Agent + Tools** (done) | Base `Agent` loop, typed tool layer, 4 safe tools across all 3 permission tiers, permission + audit | `Agent` class (plan-act-reflect, structured JSON steps), `ToolRegistry`, `memory_search`/`remember`/`read_file`/`web_fetch` tools, audit log via `store.log`/`store.recent_audit` | Agent completes a multi-step task using tools, fully logged; every tool call permission-gated; unauthorized/invalid calls fail as an observation, not a crash |
| **v0.3 Proactive + Router+** (done) | Proactive review job, richer router (multi-provider verification) | `review/weekly.py` (recent + forgotten-but-important surfacing, stored as new memory), `ModelRouter.complete_with_verification()` (agreement via local embeddings, no paid provider needed), `ask --verify` | Agent/`review` surfaces something useful unprompted; disagreement between providers is flagged, not silently picked |
| **v1.0 Personal assistant** (done) | Real integrations (Gmail/Drive via existing MCP), installable package, daily-use polish | `integrations/` (credential-free ingestion, idempotent by doc_id), `cli ingest-external`, `POST /integrations/sync`, `[project.scripts]` console entry point (`personal-llm`), `--version`, `doctor` (provider/data health check) | Real inbox/drive-aware answers proven live with real Gmail threads + a real Drive doc; `pip install -e .` produces a working `personal-llm.exe`; `doctor` is the first command to run before daily use |
| **v2 Voice + Vision** (done) | Local STT/TTS, OCR image ingestion, Gemini vision Q&A - reclassified from speculative to built (ADR 0006) | `voice/stt.py` (`faster-whisper`), `voice/tts.py` (`pyttsx3`), `vision/ocr.py` (`pytesseract`, Tesseract-optional like Ollama), `ModelRouter.describe_image()`, `cli transcribe`/`ask-voice`/`describe-image`, `POST /voice/transcribe`, `/voice/ask`, `/vision/describe`, `/vision/ingest` | TTS->STT round trip verified live with real local models (no mocks); OCR/Gemini-vision verified live too, correctly degrading since Tesseract/API key aren't provisioned yet |
| **v3 (speculative)** | Multi-device sync, SDK/plugin marketplace, continuous learning loops, voice cloning, live multi-speaker | Architecture allows it; not designed in detail yet | Revisit only if there's a second user/device, or a specific need for the harder voice/vision capabilities |

## Milestones & effort (v0.1 -> v1.0)

| Milestone | Engineering effort | Primary risk |
|---|---|---|
| Router + memory store | Small (1-2 sessions) | Python 3.14 vs 3.12 wheel mismatch |
| Ingest + retrieve + RAG | Medium | Retrieval quality on small corpora |
| KG-lite | Small | LLM extraction noise/cost |
| Interfaces (CLI/API/Streamlit) | Small-Medium | None significant - proven pattern |
| Tests + CI | Small | Mocking router cleanly |
| Agent + tools (v0.2) | Medium-Large | Tool safety, permission design |
| Real integrations (v1.0) | Medium | Auth/OAuth complexity, rate limits |
| Voice + vision (v2) | Medium | External Tesseract binary not pip-installable; vision Q&A is Gemini-only |

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Python 3.14 breaks ML wheels (chromadb/torch) | High if ignored | Blocks build | Dedicated 3.12 venv, documented in CLAUDE.md |
| Scope explosion (JARVIS trap) | High | Nothing ships | Hard P0-P3 triage in PRD; v0.1 = memory+RAG only |
| Ollama not installed / no GPU | Medium | Local path unavailable | Optional dependency; Gemini fallback always available |
| Free-tier rate limits (429s) | Medium | Flaky demos | Retry/backoff reused from `analyzer.py` |
| Prompt injection via ingested/web content | Medium | Bad tool actions (v0.2+) | Untrusted-content tagging from the first tool built |
| Privacy expectations vs implementation | Low-Medium | Trust erosion | Local-first by default, documented data flows, audit log |
| Solo-maintainer burnout on a huge vision | High | Project abandoned | Ship small, working slices every phase; v0.1 has a hard finish line |
| Tesseract OCR binary not installed | High (not installed by default on Windows) | Image ingestion unavailable | Optional dependency exactly like Ollama; clear actionable `VisionError` instead of a crash |

## Future Evolution

**5-year vision:** Personal LLM is the substrate every one of Zaid's AI projects imports; it has years of consolidated memory, a rich personal knowledge graph, a handful of trustworthy agents (research, coding, career) operating under clear permissions, and optional voice/vision modes for hands-free use.

**10-year vision (speculative, not designed):** A fully proactive digital twin capable of representing the user in low-stakes interactions (scheduling, first-pass email triage) with strong auditability, still local-first and user-owned - explicitly not a chase of "replace the user," but an amplifier under their control.
