"""Tests for the eval harness itself (evals/run_evals.py), not for the kernel.

Run as part of the regular suite: `pytest evals/ tests/ -q` from the repo root.
Kept out of tests/ deliberately - these exercise evals/run_evals.py's own machinery
(TfIdfRouter, the OOV fallback, determinism, the regression gate), not personal_llm.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from run_evals import FIXTURES, TfIdfRouter, _load_jsonl, build_regression, main


def test_tfidf_router_gives_high_similarity_for_matching_terms():
    router = TfIdfRouter(["The sourdough starter needs feeding every twelve hours."])
    doc_vec, q_vec = router.embed([
        "The sourdough starter needs feeding every twelve hours.",
        "How often does the sourdough starter need feeding?",
    ])
    cosine = sum(a * b for a, b in zip(doc_vec, q_vec))
    assert cosine > 0.25


def test_tfidf_router_out_of_vocab_query_is_not_falsely_similar():
    """A query sharing zero vocabulary with the corpus must not score as 0.5-similar
    (the Chroma zero-vector artifact this fallback exists to avoid - see the class
    docstring in run_evals.py). Uses the real fixture corpus for its vocabulary size:
    the fallback hashes into a vocab-sized space, so a handful-of-words corpus (as a
    smaller ad hoc example would have) collides too easily to demonstrate the point -
    this is a property of hashing into a small space, not specific to this fallback."""
    corpus = [d["text"] for d in _load_jsonl(FIXTURES / "corpus.jsonl")]
    router = TfIdfRouter(corpus)
    doc_vec, q_vec = router.embed([
        corpus[0],
        "What is the airspeed velocity of an unladen swallow?",
    ])
    cosine = sum(a * b for a, b in zip(doc_vec, q_vec))
    assert cosine < 0.25


def test_out_of_vocab_fallback_matches_corpus_dimensionality():
    router = TfIdfRouter(["alpha beta gamma delta epsilon"])
    fallback = router._out_of_vocab_fallback("completely unrelated words here")
    assert len(fallback) == len(router._vocab)


def test_build_regression_flags_a_failing_threshold():
    fake_results = {
        "retrieval": {"recall_at_1": 0.5, "recall_at_3": 1.0},
        "refusal": {"accuracy": 1.0},
        "hallucination": {"violations": 0},
        "prompt_injection": {"isolation_rate": 1.0},
    }
    regression = build_regression(fake_results)
    assert regression["pass"] is False
    assert regression["checks"]["retrieval.recall_at_1"]["pass"] is False
    assert regression["checks"]["refusal.accuracy"]["pass"] is True


def test_build_regression_passes_when_every_threshold_clears():
    fake_results = {
        "retrieval": {"recall_at_1": 1.0, "recall_at_3": 1.0},
        "refusal": {"accuracy": 1.0},
        "hallucination": {"violations": 0},
        "prompt_injection": {"isolation_rate": 1.0},
    }
    assert build_regression(fake_results)["pass"] is True


def test_full_eval_run_passes_and_exits_zero(tmp_path):
    assert main(["--out-dir", str(tmp_path)]) == 0
    results = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert results["regression"]["pass"] is True
    assert (tmp_path / "SCORECARD.md").exists()


def _graded_metrics(results: dict) -> dict:
    """The numbers that matter for grading a run - not the raw per-question rows,
    whose lower-ranked tie order can vary between separately-built Chroma collections
    (HNSW is an approximate index; ties beyond the clear top match are not guaranteed
    to break the same way twice - a property of the ANN library, not this eval)."""
    return {
        "correctness_accuracy": results["correctness"]["accuracy"],
        "retrieval_recall_at_1": results["retrieval"]["recall_at_1"],
        "retrieval_recall_at_3": results["retrieval"]["recall_at_3"],
        "refusal_accuracy": results["refusal"]["accuracy"],
        "hallucination_violations": results["hallucination"]["violations"],
        "prompt_injection_isolation_rate": results["prompt_injection"]["isolation_rate"],
        "regression_pass": results["regression"]["pass"],
    }


def test_full_eval_run_is_deterministic_across_runs(tmp_path):
    dir_a, dir_b = tmp_path / "a", tmp_path / "b"
    main(["--out-dir", str(dir_a)])
    main(["--out-dir", str(dir_b)])
    results_a = json.loads((dir_a / "results.json").read_text(encoding="utf-8"))
    results_b = json.loads((dir_b / "results.json").read_text(encoding="utf-8"))
    assert _graded_metrics(results_a) == _graded_metrics(results_b)


def test_script_runs_as_a_subprocess_and_writes_files(tmp_path):
    """End-to-end check that the script is directly runnable (python evals/run_evals.py),
    the way CI invokes it, not only importable."""
    script = Path(__file__).parent / "run_evals.py"
    result = subprocess.run(
        [sys.executable, str(script), "--out-dir", str(tmp_path)],
        capture_output=True, text=True, cwd=Path(__file__).parent.parent,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Overall: PASS" in result.stdout
    assert (tmp_path / "SCORECARD.md").exists()
