"""Tests for run.cmd (PROJECT-GENESIS.md Tier 6 item 43: one-click run parity).

Static-content checks only - run.cmd is a Windows batch script and this suite runs on
Linux CI, so it asserts the script's shape rather than executing it (never launches
streamlit or binds a port). jarvis-launcher's jarvis.config.json "chat UI" (default)
action for this project sets no "env" key - unlike resume-job-fit-ai/recall/ghostwriter's
entries - so run.cmd must not invent a PYTHONIOENCODING (or any other) env var.
"""
from __future__ import annotations

from pathlib import Path

RUN_CMD = Path(__file__).resolve().parents[1] / "run.cmd"


def _text() -> str:
    return RUN_CMD.read_text(encoding="utf-8")


def test_run_cmd_exists():
    assert RUN_CMD.is_file()


def test_starts_the_chat_ui_matching_jarvis_config():
    # Exact command string from jarvis.config.json's "chat UI" action - no drift.
    assert "venv\\Scripts\\python -m streamlit run src/personal_llm/interfaces/app.py" in _text()


def test_opens_the_browser_on_the_chat_ui_port():
    assert "http://localhost:8501" in _text()


def test_no_env_var_line_since_config_sets_none():
    # jarvis.config.json's "chat UI" action for Personal LLM has no "env" key, so
    # run.cmd must not invent one (e.g. PYTHONIOENCODING, borrowed from sibling repos).
    # `set "ROOT=%~dp0"` is a batch-scripting convenience for the script's own directory,
    # not an app-facing env var, so it is exempt from this guard.
    text = _text()
    assert "PYTHONIOENCODING" not in text
    for line in text.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("set ") and "root=" not in stripped:
            raise AssertionError(f"unexpected env var line: {line!r}")


def test_never_touches_gateway_auth_or_data():
    """Only the executable lines matter here - REM comments may name these by way of
    explanation without that counting as a hit. The chat UI action never talks to the
    gateway auth token or the local data stores, so run.cmd should not either."""
    executable_lines = "\n".join(
        line for line in _text().splitlines() if not line.strip().lower().startswith("rem")
    ).lower()
    assert "gateway_token" not in executable_lines
    assert "x-dreamos-token" not in executable_lines
    assert "data\\" not in executable_lines
    assert "data/" not in executable_lines


def test_no_nested_quoting():
    """Mirrors the exact bug class jarvis-launcher's launcher rewrite fixed: a quote
    nested inside a quoted string makes cmd execute the literal, corrupted text."""
    for line in _text().splitlines():
        if "cmd /k" not in line:
            continue
        assert '\\"' not in line, f"escaped quote (nesting) found in: {line!r}"
        assert '""' not in line, f"doubled quote (nesting) found in: {line!r}"
        opens = line.count('"')
        assert opens % 2 == 0, f"unbalanced quotes in: {line!r}"
