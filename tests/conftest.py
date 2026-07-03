"""Shared fixtures. FakeRouter gives deterministic, offline, hash-based embeddings and
canned completions so no test ever needs a network call or an API key."""

from __future__ import annotations

import hashlib
import math

import pytest

from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.router.schemas import Completion

EMBED_DIM = 32


def hash_embed(text: str) -> list[float]:
    vec = [0.0] * EMBED_DIM
    for word in text.lower().split():
        idx = int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBED_DIM
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


class FakeRouter:
    def __init__(self, canned_text: str = "mock answer", canned_parsed=None):
        self.canned_text = canned_text
        self.canned_parsed = canned_parsed
        self.calls: list = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [hash_embed(t) for t in texts]

    def complete(self, messages, schema=None) -> Completion:
        self.calls.append((messages, schema))
        return Completion(text=self.canned_text, parsed=self.canned_parsed, provider="fake", model="fake-model")


@pytest.fixture
def store(tmp_path):
    return MemoryStore(str(tmp_path / "test.db"))


@pytest.fixture
def vectors(tmp_path):
    return VectorStore(str(tmp_path / "chroma"))


@pytest.fixture
def router():
    return FakeRouter()
