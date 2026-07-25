"""Prompt-asset loader (PROJECT-GENESIS.md sec. 9 Tier 5 item #36, alias Tier 9
item #78): "inline prompts -> versioned files + tests". System prompts used to be
plain string constants sitting inline in rag/pipeline.py, agent/loop.py, and
review/weekly.py. That makes them hard to diff, hard to reuse, and invisible to
anything that wants to inspect "what does this app actually tell the model" without
reading Python. This module is the only place that turns a prompt NAME into prompt
TEXT; the three call sites now just call `load_prompt(name)` instead of holding
their own copy of the string.

Pure/simple on purpose - no personal_llm.router import, no model call, no network -
so it is trivial to unit test and safe to import from anywhere.

Loader strategy: `Path(__file__).parent`-relative read, not `importlib.resources`.
Checked `pyproject.toml` first: it used plain `[tool.setuptools.packages.find]`
with no `package_data`/`include_package_data`/`MANIFEST.in` entry, so a wheel
build would NOT have shipped these .txt files - setuptools does not bundle
non-`.py` files by default. Added the minimal fix for that
(`[tool.setuptools.package-data]` -> `"personal_llm.prompts" = ["*.txt"]`) so a
real wheel build includes them. Even with that fixed, this loader still reads
via `Path(__file__).parent` rather than `importlib.resources`: it is one line
simpler, needs no `files()`/context-manager ceremony for plain-text reads, and
behaves identically in the source tree, an editable install (`pip install
-e .`), and a built-and-installed wheel, since all three place `loader.py` and
its sibling `.txt` files in the same directory on disk.
"""

from __future__ import annotations

from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Return the exact text of the prompt asset `{name}.txt`.

    Raises FileNotFoundError with a helpful message if no such asset exists -
    never silently returns an empty string, since a blank system prompt is a bug
    that should fail loudly, not ship quietly.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.is_file():
        available = sorted(p.stem for p in _PROMPTS_DIR.glob("*.txt"))
        raise FileNotFoundError(
            f"No prompt asset named {name!r} (looked for {path}). "
            f"Available prompts: {available}"
        )
    return path.read_text(encoding="utf-8")
