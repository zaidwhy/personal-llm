# Personal LLM

**Your Second Brain. Your Digital Twin. Your Personal AI.**

A local-first, privacy-preserving personal memory + RAG engine - built once so future
AI projects can import it instead of rebuilding memory, retrieval, and model routing
from scratch.

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
- Runs on a **hybrid model router**: local embeddings (free, offline, no API key needed
  for ingest/retrieve) + Gemini free tier or an optional local Ollama model for generation.

## Quickstart

```powershell
cd C:\Users\Asus\projects\personal-llm
py -3.12 -m venv venv
& "venv\Scripts\python" -m pip install -r requirements.txt
& "venv\Scripts\python" -m pip install -e .

# Copy .env.example to .env and add your free Gemini key (https://aistudio.google.com/apikey)
# Ingest and retrieve work with NO key at all - only `ask` needs a chat provider.

& "venv\Scripts\python" -m personal_llm.interfaces.cli ingest "data\samples\*.md"
& "venv\Scripts\python" -m personal_llm.interfaces.cli recall "what is this project?"
& "venv\Scripts\python" -m personal_llm.interfaces.cli ask "what is this project?"

# Agent (read-only tools by default; opt in per-run to riskier tiers)
& "venv\Scripts\python" -m personal_llm.interfaces.cli agent "what is this project?"
& "venv\Scripts\python" -m personal_llm.interfaces.cli agent "look up X on example.com" --allow-network
```

Or the Streamlit chat UI:
```powershell
& "venv\Scripts\python" -m streamlit run src\personal_llm\interfaces\app.py
```

Or the FastAPI service:
```powershell
& "venv\Scripts\python" -m uvicorn personal_llm.interfaces.api:app --reload
```

## Tests

```powershell
& "venv\Scripts\python" -m pytest tests/ -q
```
54 tests, fully mocked - no API key or network required. CI runs this on every push.

## Architecture at a glance

```
Interfaces (CLI / FastAPI / Streamlit)
        |
   Personal LLM Engine
   RAG pipeline -> Reasoning -> Agent (plan-act-reflect loop)
        |
   Retrieve <-> Model Router (Gemini | Ollama) <-> Tool layer (permission-gated, audited)
        |
   Memory: SQLite (episodic/semantic/procedural) + Chroma (vectors) + Knowledge Graph
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for full diagrams and schemas, and
[ADR 0003](docs/DECISIONS/0003-agent-tool-permissions.md) for the tool permission model.

## Roadmap

| Phase | Status |
|---|---|
| v0.1 - Memory + RAG spine | **Done** |
| v0.2 - Agent + typed tool layer | **Done** |
| v0.3 - Proactive reviews, richer router | Next |
| v1.0 - Real integrations (Gmail/Drive), daily-usable | Planned |
| v2/v3 - Voice, vision, sync, SDK | Speculative |

Full detail in [`docs/ROADMAP.md`](docs/ROADMAP.md).

## License

Personal project - no license granted for reuse yet.
