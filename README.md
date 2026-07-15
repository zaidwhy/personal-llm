# Personal LLM

[![CI](https://github.com/syzayd/personal-llm/actions/workflows/ci.yml/badge.svg)](https://github.com/syzayd/personal-llm/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-107%20passed%20offline-brightgreen)
![Python](https://img.shields.io/badge/python-3.12-blue)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**Your Second Brain. Your Digital Twin. Your Personal AI.**

A local-first, privacy-preserving personal memory + RAG engine - built once so future
AI projects can import it instead of rebuilding memory, retrieval, and model routing
from scratch. It is the shared kernel behind three downstream apps:
[second-brain](https://github.com/syzayd/second-brain),
[github-pr-agent](https://github.com/syzayd/github-pr-agent), and DreamOS (an Electron
AI command bar, private until its demo video ships).

Full design docs live in [`docs/`](docs/): [PRD](docs/PRD.md), [Technical Design](docs/TDD.md),
[Architecture Blueprint](docs/ARCHITECTURE.md), [Roadmap](docs/ROADMAP.md), [Competitor analysis](docs/COMPETITORS.md).

## What it does

- **Ingest** text, markdown, or PDF files into durable memory.
- **Retrieve** semantically, ranked by similarity + importance + recency.
- **Answer** questions grounded in your own notes, with citations - and an honest
  "I don't have this in memory" instead of hallucinating.
- **Build a lightweight knowledge graph** from ingested content via LLM triple extraction.
- **Run an agent** (v0.2) toward a goal using a plan-act-reflect loop and four typed,
  permission-gated tools: `memory_search`, `remember`, `read_file` (sandboxed), and
  `web_fetch` (SSRF-guarded). Nothing runs without explicit permission for its tier, and
  every step is written to the audit log.
- **Run a proactive review** (v0.3, `review`) that surfaces recent activity and
  important-but-forgotten items without being asked - and **verify answers**
  (`ask --verify`) across every available provider, flagging disagreement instead of
  silently picking one.
- **Ingest real Gmail/Drive content** (v1.0, `ingest-external`) fetched via Claude Code's
  own already-authenticated MCP connectors - `personal_llm` holds no Google credentials
  of its own; see [ADR 0005](docs/DECISIONS/0005-external-integrations-via-mcp-bridge.md).
- **Voice** (v2): transcribe audio locally (`transcribe`, `ask-voice`) via `faster-whisper`
  - free, offline, no API key - and optionally speak the answer back (`--speak`, `pyttsx3`).
- **Vision** (v2): ingest screenshots/photos of notes via local OCR (images just work with
  `ingest`, same as PDFs), and ask Gemini about an image (`describe-image`). See
  [ADR 0006](docs/DECISIONS/0006-voice-and-vision-local-first.md).
- Runs on a **hybrid model router**: local embeddings (free, offline, no API key needed
  for ingest/retrieve) + Gemini free tier or an optional local Ollama model for generation.

## Quickstart (under 5 minutes)

```powershell
git clone https://github.com/syzayd/personal-llm
cd personal-llm
py -3.12 -m venv venv
& "venv\Scripts\python" -m pip install -r requirements.txt
& "venv\Scripts\python" -m pip install -e .

# Copy .env.example to .env and add your free Gemini key (https://aistudio.google.com/apikey)
# Ingest and retrieve work with NO key at all - only `ask` needs a chat provider.

# `pip install -e .` also installs a `personal-llm` console script - check it first:
& "venv\Scripts\personal-llm.exe" --version
& "venv\Scripts\personal-llm.exe" doctor

& "venv\Scripts\python" -m personal_llm.interfaces.cli ingest "data\samples\*.md"
& "venv\Scripts\python" -m personal_llm.interfaces.cli recall "what is this project?"
& "venv\Scripts\python" -m personal_llm.interfaces.cli ask "what is this project?"

# Agent (read-only tools by default; opt in per-run to riskier tiers)
& "venv\Scripts\python" -m personal_llm.interfaces.cli agent "what is this project?"
& "venv\Scripts\python" -m personal_llm.interfaces.cli agent "look up X on example.com" --allow-network

# Proactive review + verified answers
& "venv\Scripts\python" -m personal_llm.interfaces.cli review --days 7
& "venv\Scripts\python" -m personal_llm.interfaces.cli ask "what is this project?" --verify

# External content (Gmail/Drive fetched elsewhere, e.g. via Claude Code's MCP - see ADR 0005)
& "venv\Scripts\python" -m personal_llm.interfaces.cli ingest-external "path\to\items.json"

# Voice (local, offline, free) and vision
& "venv\Scripts\python" -m personal_llm.interfaces.cli transcribe "recording.wav"
& "venv\Scripts\python" -m personal_llm.interfaces.cli ask-voice "recording.wav" --speak
& "venv\Scripts\python" -m personal_llm.interfaces.cli ingest "screenshot.png"          # OCR, needs Tesseract installed
& "venv\Scripts\python" -m personal_llm.interfaces.cli describe-image "photo.jpg"       # needs GEMINI_API_KEY
```

Or the Streamlit chat UI:
```powershell
& "venv\Scripts\python" -m streamlit run src\personal_llm\interfaces\app.py
```

Or the FastAPI service:
```powershell
& "venv\Scripts\python" -m uvicorn personal_llm.interfaces.api:app --reload
```
The HTTP gateway is CSRF-hardened: every request needs the `X-DreamOS-Token` header
(value auto-created at `data/gateway_token` on first request), and anything carrying a
browser `Origin` header is rejected outright. The CLI and Streamlit UI use the engine
in-process and need no token.

## Demo

<!-- TODO(zaid): record a real 30-second GIF - ingest a note, ask a question, show the
cited answer + the honest refusal on a question memory can't answer. Never fabricate. -->
Demo GIF coming soon. Until then, the Quickstart above reproduces the full flow in
under 5 minutes with no API key.

## Tests

```powershell
& "venv\Scripts\python" -m pytest tests/ -q
```
107 tests, fully mocked - no API key, network, real model, or real Tesseract binary
required. CI runs this on every push (keyless by design).

## Architecture at a glance

```
Interfaces (CLI / FastAPI / Streamlit)
        |
   Personal LLM Engine
   RAG pipeline -> Reasoning -> Agent (plan-act-reflect loop) -> Proactive review
        |
   Retrieve <-> Model Router (Gemini | Ollama, verified) <-> Tool layer (permission-gated, audited)
        |                                                          |
   Memory: SQLite (episodic/semantic/procedural) + Chroma (vectors) + Knowledge Graph
        ^                                                          |
   External integrations (Gmail/Drive, ingested idempotently)   Voice (STT/TTS) + Vision (OCR/Gemini)
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full diagrams and schemas,
[ADR 0003](docs/DECISIONS/0003-agent-tool-permissions.md) for the tool permission model,
[ADR 0004](docs/DECISIONS/0004-router-verification.md) for multi-provider verification,
[ADR 0005](docs/DECISIONS/0005-external-integrations-via-mcp-bridge.md) for external
integrations (including the rule that real synced content must never enter this repo),
and [ADR 0006](docs/DECISIONS/0006-voice-and-vision-local-first.md) for voice/vision.

## Roadmap

| Phase | Status |
|---|---|
| v0.1 - Memory + RAG spine | **Done** |
| v0.2 - Agent + typed tool layer | **Done** |
| v0.3 - Proactive review, router verification | **Done** |
| v1.0 - Real integrations (Gmail/Drive), installable package, `doctor` | **Done** |
| v2 - Voice (STT/TTS), vision (OCR + Gemini) | **Done** |
| v3 - Multi-device sync, SDK/marketplace, voice cloning | Speculative |

Full detail in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). The one hard rule: the test suite stays fully
offline and keyless.

## License

[MIT](LICENSE).
