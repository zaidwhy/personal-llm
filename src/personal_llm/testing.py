"""Offline test double for ModelRouter: deterministic hash-based embeddings and canned
completions, so tests and evals never need a network call or an API key.

Extracted from tests/conftest.py (2026-09-16) so evals/ can import the same double
instead of re-implementing it - this is the package's own testing surface, not test-only
code, which is why it lives under src/personal_llm/ rather than tests/.
"""

from __future__ import annotations

import hashlib
import math

from personal_llm.router.schemas import Completion, VerifiedCompletion

EMBED_DIM = 32


def hash_embed(text: str) -> list[float]:
    """A cheap, deterministic stand-in for a real embedding model: same text always
    maps to the same vector, and unrelated texts land far apart in cosine terms."""
    vec = [0.0] * EMBED_DIM
    for word in text.lower().split():
        idx = int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeRouter:
    """Drop-in replacement for ModelRouter. `script` (a list of parsed Pydantic models)
    lets a caller queue up exact responses, popped one per `complete()` call; otherwise
    every call returns `canned_text`/`canned_parsed`. Every call is recorded in `.calls`
    so a test or eval can assert on exactly what messages the pipeline constructed."""

    def __init__(
        self,
        canned_text: str = "mock answer",
        canned_parsed=None,
        script: list | None = None,
        verify_result: VerifiedCompletion | None = None,
    ):
        self.canned_text = canned_text
        self.canned_parsed = canned_parsed
        self.script = list(script) if script is not None else None
        self.verify_result = verify_result
        self.calls: list = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]

    def complete(self, messages, schema=None) -> Completion:
        self.calls.append((messages, schema))
        if self.script:
            parsed = self.script.pop(0)
            return Completion(text=parsed.model_dump_json(), parsed=parsed, provider="fake", model="fake-model")
        return Completion(text=self.canned_text, parsed=self.canned_parsed, provider="fake", model="fake-model")

    def complete_with_verification(self, messages, schema=None) -> VerifiedCompletion:
        if self.verify_result is not None:
            return self.verify_result
        return VerifiedCompletion(primary=self.complete(messages, schema=schema))

    def provider_status(self) -> dict[str, bool]:
        return {"fake": True}
