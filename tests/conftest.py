"""Shared fixtures. FakeRouter gives deterministic, offline, hash-based embeddings and
canned completions so no test ever needs a network call or an API key."""

from __future__ import annotations

import pytest

from personal_llm import config
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.testing import EMBED_DIM, FakeRouter, hash_embed  # noqa: F401 (re-exported for existing tests)


@pytest.fixture(autouse=True)
def _isolated_nexus_data_dir(tmp_path, monkeypatch):
    """get_settings() is called unconditionally by several modules (e.g.
    memory.retrieve.semantic_search) even in tests that build their own store/vectors
    from tmp_path fixtures. Without this, every test run resolves NEXUS_DATA_DIR to the
    real production data root and mkdir's into it. Point it at a per-test tmp dir and
    drop the cached singleton so the override actually takes effect."""
    monkeypatch.setenv("NEXUS_DATA_DIR", str(tmp_path / "nexus_data"))
    config.reset_settings()
    yield
    config.reset_settings()


@pytest.fixture
def store(tmp_path):
    return MemoryStore(str(tmp_path / "test.db"))


@pytest.fixture
def vectors(tmp_path):
    return VectorStore(str(tmp_path / "chroma"))


@pytest.fixture
def router():
    return FakeRouter()
