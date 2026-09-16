"""Tests for the Space demo's app logic (space/app.py), not the kernel.

Deliberately NOT wired into the main `pytest tests/` run: unlike the rest of this repo,
these download real sentence-transformers weights from the Hugging Face Hub on first
run, so they are not offline/keyless. Run manually before pushing to the Space (see
DEPLOYMENT.md's "Local test before pushing"):

    pip install -r space/requirements.txt
    pytest space/test_app.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import app


def test_retrieve_finds_the_relevant_document():
    result = app.retrieve("What did the TCMF benchmark find?")
    assert "civilizationos" in result
    assert "recall at 5" in result or "0.02" in result


def test_retrieve_on_empty_question_prompts_rather_than_erroring():
    result = app.retrieve("")
    assert "Type a question" in result


def test_retrieve_returns_multiple_ranked_results():
    result = app.retrieve("How many merged pull requests and open source stars?")
    assert "open-source" in result
    assert "similarity" in result


def test_answer_without_a_key_points_to_the_free_key_and_does_not_call_gemini():
    result = app.answer("How many tests does personal-llm have?", "")
    assert "aistudio.google.com/apikey" in result
    assert "never stored or logged" in result


def test_answer_on_empty_question_prompts_rather_than_erroring():
    assert "first" in app.answer("", "some-key").lower()


def test_answer_with_an_invalid_key_surfaces_a_clean_error_not_a_traceback():
    result = app.answer("How many tests does personal-llm have?", "definitely-not-a-real-key")
    assert "rejected" in result.lower() or "invalid" in result.lower()
    assert "Traceback" not in result


def test_corpus_facts_are_present_and_ingested():
    """Every corpus doc should be independently retrievable - a broken ingest for one
    document would otherwise hide silently behind the others still working."""
    from corpus import CORPUS

    for doc in CORPUS:
        result = app.retrieve(doc["text"][:60])
        assert doc["doc_id"] in result, f"{doc['doc_id']} did not retrieve for its own opening text"
