"""Ranked semantic retrieval: similarity + importance + recency (docs/TDD.md section 1)."""

from __future__ import annotations

import math
from datetime import datetime, timezone

from pydantic import BaseModel

from personal_llm.config import get_settings
from personal_llm.router import ModelRouter

from .store import MemoryStore
from .vectors import VectorStore


class RetrievedChunk(BaseModel):
    chunk_id: str
    doc_id: str
    text: str
    source: str
    similarity: float
    importance: float
    rank_score: float


def _recency_decay(last_accessed_or_created: str, half_life_days: float) -> float:
    try:
        ts = datetime.fromisoformat(last_accessed_or_created)
    except ValueError:
        return 0.5
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    days = max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)
    return math.exp(-days / half_life_days)


def semantic_search(
    store: MemoryStore,
    vectors: VectorStore,
    router: ModelRouter,
    query: str,
    k: int | None = None,
    touch: bool = True,
) -> list[RetrievedChunk]:
    settings = get_settings()
    k = k or settings.retrieval_top_k

    query_vector = router.embed([query])[0]
    hits = vectors.query(query_vector, k=k)
    if not hits:
        return []

    chunk_ids = [hit_id for hit_id, _sim, _meta in hits]
    chunks_by_id = {c.id: c for c in store.get_chunks(chunk_ids)}
    memories_by_vector_id = store.get_memories_by_vector_ids(chunk_ids)

    results: list[RetrievedChunk] = []
    for hit_id, similarity, meta in hits:
        chunk = chunks_by_id.get(hit_id)
        if chunk is None:
            continue
        memory = memories_by_vector_id.get(hit_id)
        importance = memory.importance if memory else 0.5
        recency_basis = (memory.last_accessed or memory.created_at) if memory else chunk.created_at
        recency = _recency_decay(recency_basis, settings.memory_recency_half_life_days)
        rank_score = 0.6 * similarity + 0.2 * importance + 0.2 * recency

        results.append(
            RetrievedChunk(
                chunk_id=chunk.id,
                doc_id=chunk.doc_id,
                text=chunk.text,
                source=memory.source if memory else meta.get("doc_id", ""),
                similarity=similarity,
                importance=importance,
                rank_score=rank_score,
            )
        )
        if touch and memory:
            store.touch_memory(memory.id)

    results.sort(key=lambda r: r.rank_score, reverse=True)
    return results
