# Personal LLM - Claude Instructions

Local-first personal memory + RAG engine. The reusable "brain" future projects (Recall, CivilizationOS, portfolio) import as a package instead of rebuilding memory/RAG/routing.

Full design docs: `docs/PRD.md`, `docs/TDD.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`.

## Run (one terminal)

```powershell
cd C:\Users\Asus\projects\ai-ecosystem\personal-llm
& "venv\Scripts\python" -m personal_llm.interfaces.cli --help
```

Streamlit chat:
```powershell
& "venv\Scripts\python" -m streamlit run src\personal_llm\interfaces\app.py
```

FastAPI service:
```powershell
& "venv\Scripts\python" -m uvicorn personal_llm.interfaces.api:app --reload
```

## Python environment

- Venv folder is `venv`, **Python 3.12** (NOT 3.14 - torch/chromadb/sentence-transformers wheels lag on 3.14). Create with:
  `py -3.12 -m venv venv`
- Install deps: `& "venv\Scripts\python" -m pip install -r requirements.txt` then `& "venv\Scripts\python" -m pip install -e .`

## Tests

```powershell
& "venv\Scripts\python" -m pytest tests/ -q
```
All LLM calls are mocked in tests - no API key needed. GitHub Actions runs pytest on every push to main (`.github/workflows/ci.yml`).

## Env

- `.env` at repo root needs `GEMINI_API_KEY` (free tier: https://aistudio.google.com/apikey). Template in `.env.example`. Never read `.env` directly; ask the user for values.
- Local embeddings (`sentence-transformers`) mean ingest/retrieve work with **no API key at all** - only `ask` (generation) needs Gemini or a running Ollama.
- Ollama is optional. If `OLLAMA_HOST` is unreachable, the router falls back to Gemini automatically.

## Architecture notes

- Engine is UI-agnostic: `src/personal_llm/` is the importable package. `interfaces/` (CLI, FastAPI, Streamlit) are thin clients over it - same pattern as `analyzer.py` in resume-job-fit-ai.
- Memory lives in SQLite (`data/personal_llm.db`) + Chroma (`data/chroma/`), both gitignored and local to the machine.
- Model router (`router/router.py`) is the only place that calls out to Gemini/Ollama - swap or add providers there, nowhere else.

## Logs and handoffs (required every session)

- Master log: `MASTER_LOG.md` - append only, read just the tail.
- Handoffs: `handoffs/HANDOFF-YYYY-MM-DD-HHMM.md`.
- Before ending a session: update the master log AND write a handoff (or run `/wrap`).

## Other gotchas

- Never use the em dash character (U+2014) anywhere; use " - " instead.
- `data/` is gitignored and ephemeral - regenerate via `ingest` rather than committing memory/vector data.
