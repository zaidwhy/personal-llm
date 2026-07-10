# Contributing

Thanks for looking at Personal LLM. It is a personal project, but issues and small,
focused PRs are welcome.

## Ground rules

1. **Tests stay offline and keyless.** Every test must run with no API key, no network,
   no real model, and no system binaries (Tesseract, ffmpeg). Inject fakes the way
   `tests/conftest.py` does (`FakeRouter` with hash-based embeddings). A PR that adds a
   networked test will be asked to mock it.
2. **One concern per PR.** Small and surgical beats broad and clever.
3. **Model calls go through the router.** `router/router.py` is the only place that
   talks to Gemini/Ollama; new providers plug in there, nowhere else.
4. **Interfaces stay thin.** CLI / FastAPI / Streamlit are clients of the engine; logic
   belongs in the engine packages, not in the interface layer.

## Dev setup

Follow the Quickstart in [README.md](README.md) (Python 3.12), then:

```powershell
& "venv\Scripts\python" -m pytest tests/ -q
```

All 100 tests should pass before and after your change. CI runs the same command on
every push and PR.

## Design context

Architecture decisions are recorded in `docs/DECISIONS/` (ADRs). If your change alters
a recorded decision, update or add an ADR in the same PR.
