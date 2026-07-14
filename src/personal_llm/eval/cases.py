"""Built-in prompt-regression eval cases over the two pipelines with real system
prompts baked into their message construction: `rag.pipeline.ask` and
`review.weekly.generate_review`.

`_ScriptedRouter` is a minimal chat/embed double - deliberately not imported from
`tests/conftest.py`'s `FakeRouter`, because these cases need to run from the `eval` CLI
command too, and `tests/` is not an importable package at runtime. It mirrors just the
surface `ModelRouter` callers use (`embed`, `complete`, `complete_with_verification`).
"""

from __future__ import annotations

import hashlib
import math
import tempfile
from pathlib import Path

from personal_llm.memory.ingest import ingest_text
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.types import MemoryRecord
from personal_llm.memory.vectors import VectorStore
from personal_llm.rag.pipeline import NOT_IN_MEMORY, ask
from personal_llm.review.weekly import ReviewInsights, generate_review
from personal_llm.router.schemas import Completion, VerifiedCompletion

from .harness import Assertion, EvalCase

_EMBED_DIM = 32


def _hash_embed(text: str) -> list[float]:
    """Deterministic, offline stand-in for a real embedder - same hashing trick as
    tests/conftest.py's FakeRouter, so semantically similar text lands near itself in
    the real Chroma index without needing sentence-transformers loaded.
    """
    vec = [0.0] * _EMBED_DIM
    for word in text.lower().split():
        idx = int(hashlib.sha256(word.encode()).hexdigest(), 16) % _EMBED_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class _ScriptedRouter:
    """Canned chat/embed responses, no network - just enough of `ModelRouter`'s surface
    for the pipelines this module evaluates.
    """

    def __init__(self, canned_text: str = "eval answer", canned_parsed=None) -> None:
        self.canned_text = canned_text
        self.canned_parsed = canned_parsed

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [_hash_embed(t) for t in texts]

    def complete(self, messages, schema=None) -> Completion:
        return Completion(text=self.canned_text, parsed=self.canned_parsed, provider="eval", model="eval-model")

    def complete_with_verification(self, messages, schema=None) -> VerifiedCompletion:
        return VerifiedCompletion(primary=self.complete(messages, schema=schema))


def _rag_grounded_case() -> EvalCase:
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(str(Path(tmp) / "test.db"))
            vectors = VectorStore(str(Path(tmp) / "chroma"))
            router = _ScriptedRouter(canned_text="Zaid is building Personal LLM.")
            ingest_text(
                store, vectors, router,
                text="Zaid is building Personal LLM, a local-first memory engine.",
                doc_id="doc-1", source="notes.md", extract_kg=False,
            )
            result = ask(store, vectors, router, "What is Zaid building?")
            vectors.close()
            return result

    return EvalCase(
        name="rag_grounded_answer_cites_source",
        run=run,
        assertions=[
            Assertion("answer is grounded", lambda a: a.grounded is True),
            Assertion("at least one source is cited", lambda a: len(a.sources) >= 1),
            Assertion("cited source matches the ingested doc", lambda a: a.sources[0].source == "notes.md"),
        ],
    )


def _rag_ungrounded_case() -> EvalCase:
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(str(Path(tmp) / "test.db"))
            vectors = VectorStore(str(Path(tmp) / "chroma"))
            router = _ScriptedRouter()
            result = ask(store, vectors, router, "anything at all, memory is empty")
            vectors.close()
            return result

    return EvalCase(
        name="rag_empty_memory_says_not_in_memory",
        run=run,
        assertions=[
            Assertion("answer is not grounded", lambda a: a.grounded is False),
            Assertion("text is the honest not-in-memory message", lambda a: a.text == NOT_IN_MEMORY),
            Assertion("no sources are fabricated", lambda a: a.sources == []),
        ],
    )


def _review_report_shape_case() -> EvalCase:
    def run():
        with tempfile.TemporaryDirectory() as tmp:
            store = MemoryStore(str(Path(tmp) / "test.db"))
            store.add_memory(MemoryRecord(kind="episodic", content="Shipped the eval harness.", source="chat", importance=0.5))
            insights = ReviewInsights(
                highlights=["Shipped the eval harness."],
                forgotten_worth_revisiting=[],
                suggested_actions=["Wire it into CI."],
            )
            router = _ScriptedRouter(canned_parsed=insights)
            return generate_review(store, router, days=7)

    return EvalCase(
        name="review_report_has_expected_shape",
        run=run,
        assertions=[
            Assertion("recent_count reflects the ingested memory", lambda r: r.recent_count >= 1),
            Assertion("highlights are carried through from the model", lambda r: r.insights.highlights == ["Shipped the eval harness."]),
            Assertion("suggested_actions are carried through from the model", lambda r: len(r.insights.suggested_actions) == 1),
        ],
    )


def builtin_cases() -> list[EvalCase]:
    """The current set of prompt-regression cases. Extend this list as more
    prompt-dependent pipelines (agent, ingest KG extraction, ...) grow eval coverage.
    """
    return [_rag_grounded_case(), _rag_ungrounded_case(), _review_report_shape_case()]
