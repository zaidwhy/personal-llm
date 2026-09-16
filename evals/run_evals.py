"""Offline eval suite for the personal-llm kernel. No network call, no API key.

Runs seven suites against a fixed, tiny fictional corpus (evals/fixtures/) so results
are deterministic and reproducible on any machine:

    correctness       does the answer actually ground on the right document?
    retrieval         recall@1 / recall@3 over the QA set
    refusal           unanswerable questions get NOT_IN_MEMORY, answerable ones don't
    hallucination     every cited source was actually retrieved (never invented)
    latency           local engine overhead per ask() call (excludes real LLM latency -
                      the router is a fake, so this measures ingest/retrieve/prompt-build
                      cost only, not what a real provider would add)
    prompt_injection  retrieved (untrusted) text never reaches the system-role message
    regression        the five suites above against fixed pass/fail thresholds

"cost" is deliberately not a suite: with a fake router, no real token pricing is
observed, and reporting a dollar figure here would be fabricated. What IS measured
(prompt/context size) is folded into the latency report as an honest proxy instead.

Usage:  python evals/run_evals.py [--out-dir evals]
Writes evals/results.json and evals/SCORECARD.md. Exits 1 if any regression
threshold fails (see REGRESSION_THRESHOLDS below).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from personal_llm.memory.ingest import ingest_text
from personal_llm.memory.retrieve import semantic_search
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.prompts import load_prompt
from personal_llm.rag.pipeline import NOT_IN_MEMORY, ask
from personal_llm.testing import FakeRouter

FIXTURES = Path(__file__).parent / "fixtures"

_TOKEN_RE = re.compile(r"[a-z]+")
# Not an exhaustive stopword list - just enough that shared function words don't
# dominate a 32-dim hash-style embedding; see TfIdfRouter docstring below.
_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "to", "of", "in", "on", "at",
    "for", "and", "or", "my", "i", "it", "its", "that", "this", "with", "from", "by",
    "as", "do", "does", "did", "what", "how", "who", "where", "when", "should", "need",
    "needs", "if", "me", "any", "before", "after",
}


class TfIdfRouter(FakeRouter):
    """FakeRouter with a real (if tiny) retrieval signal instead of hash_embed.

    hash_embed sums a one-hot-per-word hash into 32 dimensions - fine for the existing
    unit tests, which deliberately use maximally distinct topics (a cat vs. quantum
    physics), but too lossy to evaluate retrieval quality over a realistic multi-topic
    corpus: with only 32 buckets, shared function words ("how", "does", "my") collide
    across completely unrelated documents and dominate the cosine score. TF-IDF over a
    known, fixed vocabulary fixes that the same way a real embedding model implicitly
    does: common words contribute little, the words that actually distinguish one note
    from another contribute most. Still fully deterministic and offline - no model, no
    network - so it belongs in evals/, not in personal_llm/testing.py where the crude
    version is the documented, intentional behaviour for unit tests.

    Idf is built ONLY from the corpus documents being ingested, never from queries:
    document frequency is a property of the corpus, and treating a query as "another
    document" for df purposes would suppress exactly the terms that make it match
    (a term shared by a query and its one matching document would look artificially
    common).

    A query whose words are entirely absent from the corpus vocabulary would
    otherwise embed as a true zero vector - and because the kernel's Chroma-side
    similarity formula (`1 - squared_L2/2`) assumes both sides are unit vectors, a
    zero vector against any real unit vector always comes out to exactly 0.5
    similarity, not 0: an artifact of the formula, not a real "somewhat related"
    signal. `embed()` falls back to a hash of the query's own words into the SAME
    vocabulary-sized space (Chroma requires one fixed dimensionality per collection,
    so the fallback can't just reuse the unrelated 32-dim hash_embed) - a direction
    with no relationship to the corpus vocabulary, which correctly reads as
    dissimilar to every real document.
    """

    def __init__(self, corpus_texts: list[str], **kwargs):
        super().__init__(**kwargs)
        docs = [self._tokenize(t) for t in corpus_texts]
        vocab_terms = sorted({term for doc in docs for term in doc})
        self._vocab = {term: i for i, term in enumerate(vocab_terms)}
        n_docs = len(docs) or 1
        doc_freq = Counter(term for doc in docs for term in set(doc))
        self._idf = [math.log(n_docs / (1 + doc_freq[term])) + 1.0 for term in vocab_terms]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        return [w for w in _TOKEN_RE.findall(text.lower()) if w not in _STOPWORDS and len(w) > 2]

    def _out_of_vocab_fallback(self, text: str) -> list[float]:
        """Same dimensionality as the real TF-IDF vectors (Chroma requires a fixed
        dimension per collection), but the direction comes purely from a hash of the
        query's own words - unrelated to which corpus terms occupy which index - so
        it lands nowhere near any real document's vector. See class docstring."""
        dim = len(self._vocab) or 1
        vec = [0.0] * dim
        words = re.findall(r"[a-z]+", text.lower())
        for word in words or [text]:
            idx = int(hashlib.sha256(word.encode()).hexdigest(), 16) % dim
            vec[idx] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            counts = Counter(self._tokenize(text))
            vec = [0.0] * len(self._vocab)
            for term, count in counts.items():
                idx = self._vocab.get(term)
                if idx is not None:
                    vec[idx] = count * self._idf[idx]
            norm = math.sqrt(sum(v * v for v in vec))
            if norm == 0.0:
                # No word in this text is in the corpus vocabulary at all.
                vectors.append(self._out_of_vocab_fallback(text))
                continue
            vectors.append([v / norm for v in vec])
        return vectors

REGRESSION_THRESHOLDS = {
    "retrieval.recall_at_1": ("gte", 0.80),
    "retrieval.recall_at_3": ("gte", 1.00),
    "refusal.accuracy": ("gte", 1.00),
    "hallucination.violations": ("eq", 0),
    "prompt_injection.isolation_rate": ("gte", 1.00),
}


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _build_kernel(tmp_dir: Path, router: FakeRouter | None = None):
    store = MemoryStore(str(tmp_dir / "eval.db"))
    vectors = VectorStore(str(tmp_dir / "eval_chroma"))
    return store, vectors, router or FakeRouter(canned_text="mock answer")


def _ingest_corpus(store, vectors, router, docs: list[dict]) -> None:
    for doc in docs:
        ingest_text(store, vectors, router, text=doc["text"], doc_id=doc["doc_id"], source="eval-corpus", extract_kg=False)


# ---------------------------------------------------------------- correctness

def run_correctness(store, vectors, router, qa: list[dict], k: int = 3) -> dict:
    """For each answerable question: does ask() ground on the expected document and
    does the context actually contain the expected fact (proving real grounding, not
    a lucky doc_id match)? k is fixed (rather than the settings default) so this suite
    and `run_hallucination` compare against the same retrieval window."""
    answerable = [q for q in qa if q["expected_doc_id"]]
    checks = []
    for q in answerable:
        answer = ask(store, vectors, router, q["question"], k=k)
        cited_docs = {s.doc_id for s in answer.sources}
        context_sent = router.calls[-1][0][1].content if router.calls else ""
        grounded_correctly = q["expected_doc_id"] in cited_docs
        context_has_fact = q["expected_context_substring"] in context_sent
        checks.append({
            "question": q["question"],
            "expected_doc_id": q["expected_doc_id"],
            "cited_docs": sorted(cited_docs),
            "grounded_correctly": grounded_correctly,
            "context_has_expected_fact": context_has_fact,
            "pass": grounded_correctly and context_has_fact,
        })
    passed = sum(c["pass"] for c in checks)
    return {"total": len(checks), "passed": passed, "accuracy": passed / len(checks) if checks else 0.0, "checks": checks}


# ------------------------------------------------------------------ retrieval

def run_retrieval(store, vectors, router, qa: list[dict], k: int = 3) -> dict:
    """recall@1 and recall@k over the answerable questions: does semantic_search put
    the correct document in the top-1 / top-k results?"""
    answerable = [q for q in qa if q["expected_doc_id"]]
    hit_at_1, hit_at_k, rows = 0, 0, []
    for q in answerable:
        results = semantic_search(store, vectors, router, q["question"], k=k)
        doc_ids = [r.doc_id for r in results]
        at1 = doc_ids[:1] == [q["expected_doc_id"]]
        atk = q["expected_doc_id"] in doc_ids
        hit_at_1 += at1
        hit_at_k += atk
        rows.append({"question": q["question"], "expected_doc_id": q["expected_doc_id"], "top_k_doc_ids": doc_ids, "hit_at_1": at1, f"hit_at_{k}": atk})
    n = len(answerable) or 1
    return {"total": len(answerable), "recall_at_1": hit_at_1 / n, f"recall_at_{k}": hit_at_k / n, "rows": rows}


# --------------------------------------------------------------------- refusal

def run_refusal(store, vectors, router, qa: list[dict], k: int = 3) -> dict:
    """Unanswerable questions must refuse (NOT_IN_MEMORY, grounded=False); answerable
    ones must not refuse. Both directions matter - an over-eager refusal gate is as
    wrong as a hallucinating one."""
    checks = []
    for q in qa:
        answer = ask(store, vectors, router, q["question"], k=k)
        should_refuse = q["expected_doc_id"] is None
        did_refuse = not answer.grounded and answer.text == NOT_IN_MEMORY
        checks.append({"question": q["question"], "should_refuse": should_refuse, "did_refuse": did_refuse, "pass": should_refuse == did_refuse})
    passed = sum(c["pass"] for c in checks)
    return {"total": len(checks), "passed": passed, "accuracy": passed / len(checks) if checks else 0.0, "checks": checks}


# --------------------------------------------------------------- hallucination

def run_hallucination(store, vectors, router, qa: list[dict], k: int = 3) -> dict:
    """Every doc_id an Answer cites must be among the doc_ids semantic_search actually
    retrieved for that question - the code must never let a citation appear that
    wasn't grounded in real retrieval."""
    answerable = [q for q in qa if q["expected_doc_id"]]
    violations, rows = [], []
    for q in answerable:
        retrieved = {r.doc_id for r in semantic_search(store, vectors, router, q["question"], k=k)}
        answer = ask(store, vectors, router, q["question"], k=k)
        cited = {s.doc_id for s in answer.sources}
        invented = cited - retrieved
        if invented:
            violations.append({"question": q["question"], "invented_doc_ids": sorted(invented)})
        rows.append({"question": q["question"], "cited": sorted(cited), "retrieved": sorted(retrieved)})
    return {"total": len(answerable), "violations": len(violations), "violation_details": violations, "rows": rows}


# -------------------------------------------------------------------- latency

def run_latency(store, vectors, router, qa: list[dict], repeats: int = 20) -> dict:
    """Wall-clock time for ask() with a fake (instant) router - this isolates the
    kernel's own overhead (chunking already done, retrieval, prompt assembly, SQLite
    writes) from provider latency, which is not observable offline."""
    question = qa[0]["question"]
    durations_ms, context_chars = [], []
    for _ in range(repeats):
        start = time.perf_counter()
        ask(store, vectors, router, question, k=3)
        durations_ms.append((time.perf_counter() - start) * 1000)
        context_chars.append(len(router.calls[-1][0][1].content))
    durations_ms.sort()
    p50 = statistics.median(durations_ms)
    p95 = durations_ms[min(len(durations_ms) - 1, int(len(durations_ms) * 0.95))]
    return {
        "repeats": repeats,
        "p50_ms": round(p50, 2),
        "p95_ms": round(p95, 2),
        "avg_context_chars": round(statistics.mean(context_chars), 1),
        "note": "local engine overhead only (fake router is instant) - excludes real provider latency",
    }


# ------------------------------------------------------------- prompt_injection

def run_prompt_injection(tmp_dir: Path, injection_doc: dict, injection_q: dict) -> dict:
    """Ingest a document containing an embedded instruction and ask the question that
    retrieves it. The system-role message must stay exactly the loaded system prompt;
    the injected text may only ever appear inside the user-role <context> block. This
    tests the pipeline's message-construction code, not whether a real model obeys an
    injected instruction (that needs a live model and is out of scope offline)."""
    injection_dir = tmp_dir / "injection"
    injection_dir.mkdir()
    injection_router = TfIdfRouter([injection_doc["text"]], canned_text="mock answer")
    store, vectors, router = _build_kernel(injection_dir, router=injection_router)
    try:
        ingest_text(store, vectors, router, text=injection_doc["text"], doc_id=injection_doc["doc_id"], source="eval-injection", extract_kg=False)
        ask(store, vectors, router, injection_q["question"])
    finally:
        vectors.close()
    messages = router.calls[-1][0]
    system_message = next(m for m in messages if m.role == "system")
    user_message = next(m for m in messages if m.role == "user")
    system_untouched = system_message.content == load_prompt("rag_system")
    isolated = "SYSTEM OVERRIDE" not in system_message.content and "SYSTEM OVERRIDE" in user_message.content
    return {
        "system_prompt_untouched": system_untouched,
        "injected_content_isolated_to_user_message": isolated,
        "isolation_rate": 1.0 if (system_untouched and isolated) else 0.0,
    }


# -------------------------------------------------------------------- report

def _check_threshold(value, rule) -> bool:
    op, target = rule
    return value >= target if op == "gte" else value == target


def build_regression(results: dict) -> dict:
    checks = {}
    for key, rule in REGRESSION_THRESHOLDS.items():
        suite, field = key.split(".")
        value = results[suite][field]
        checks[key] = {"value": value, "threshold": rule, "pass": _check_threshold(value, rule)}
    return {"checks": checks, "pass": all(c["pass"] for c in checks.values())}


def render_scorecard(results: dict) -> str:
    lines = [
        "# personal-llm eval scorecard", "",
        "Generated by `evals/run_evals.py`. Offline, keyless, fully deterministic.",
        "LLM completions come from a canned FakeRouter; embeddings come from a deterministic "
        "TF-IDF stand-in (see `TfIdfRouter` in the script) rather than the production "
        "sentence-transformers model - these suites test the RAG pipeline's *logic* "
        "(does it retrieve, ground, cite, and refuse correctly), not production embedding "
        "quality, which needs a live model and is out of scope for an offline suite.",
        "",
    ]
    c = results["correctness"]
    lines += [f"## Correctness: {c['passed']}/{c['total']} ({c['accuracy']:.0%})", ""]
    r = results["retrieval"]
    lines += [f"## Retrieval: recall@1 = {r['recall_at_1']:.0%}, recall@3 = {r['recall_at_3']:.0%} (n={r['total']})", ""]
    ref = results["refusal"]
    lines += [f"## Refusal: {ref['passed']}/{ref['total']} correct ({ref['accuracy']:.0%})", ""]
    h = results["hallucination"]
    lines += [f"## Hallucination: {h['violations']} violation(s) out of {h['total']} answers", ""]
    lat = results["latency"]
    lines += [f"## Latency (local engine overhead, fake provider): p50 {lat['p50_ms']}ms, p95 {lat['p95_ms']}ms, avg context {lat['avg_context_chars']} chars", ""]
    pi = results["prompt_injection"]
    lines += [f"## Prompt injection isolation: {'PASS' if pi['isolation_rate'] == 1.0 else 'FAIL'} (system prompt untouched: {pi['system_prompt_untouched']}, injected content isolated: {pi['injected_content_isolated_to_user_message']})", ""]
    reg = results["regression"]
    lines += ["## Regression gate", "", "| Metric | Value | Threshold | Result |", "|---|---|---|---|"]
    for key, check in reg["checks"].items():
        op, target = check["threshold"]
        symbol = ">=" if op == "gte" else "=="
        lines.append(f"| {key} | {check['value']} | {symbol} {target} | {'PASS' if check['pass'] else 'FAIL'} |")
    lines += ["", f"**Overall: {'PASS' if reg['pass'] else 'FAIL'}**", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=Path(__file__).parent)
    args = parser.parse_args(argv)

    corpus = _load_jsonl(FIXTURES / "corpus.jsonl")
    qa = _load_jsonl(FIXTURES / "qa.jsonl")
    injection_rows = _load_jsonl(FIXTURES / "injection.jsonl")
    injection_doc, injection_q = injection_rows[0], injection_rows[1]

    shared_router = TfIdfRouter([doc["text"] for doc in corpus], canned_text="mock answer")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        store, vectors, router = _build_kernel(tmp_dir, router=shared_router)
        try:
            _ingest_corpus(store, vectors, router, corpus)
            results = {
                "correctness": run_correctness(store, vectors, router, qa),
                "retrieval": run_retrieval(store, vectors, router, qa),
                "refusal": run_refusal(store, vectors, router, qa),
                "hallucination": run_hallucination(store, vectors, router, qa),
                "latency": run_latency(store, vectors, router, qa),
            }
        finally:
            # Chroma's PersistentClient holds chroma.sqlite3 open on Windows until this
            # runs; without it, TemporaryDirectory's teardown hits WinError 32.
            vectors.close()
        results["prompt_injection"] = run_prompt_injection(tmp_dir, injection_doc, injection_q)
    results["regression"] = build_regression(results)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    (args.out_dir / "SCORECARD.md").write_text(render_scorecard(results), encoding="utf-8")

    print(render_scorecard(results))
    return 0 if results["regression"]["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
