"""Idempotently turns externally-fetched items into memory via the normal ingest pipeline.

This module never fetches anything itself and has no credentials of its own - the fetch
happens outside personal_llm (docs/DECISIONS/0005). Re-running sync with the same items
is safe: already-ingested doc_ids are skipped rather than duplicated.
"""

from __future__ import annotations

from personal_llm.memory.ingest import ingest_text
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.router import ModelRouter

from .schemas import ExternalItem, SyncResult


def _doc_id(item: ExternalItem) -> str:
    return f"{item.source}:{item.external_id}"


def sync_external_items(
    store: MemoryStore, vectors: VectorStore, router: ModelRouter, items: list[ExternalItem]
) -> SyncResult:
    ingested = 0
    skipped = 0
    doc_ids: list[str] = []

    for item in items:
        doc_id = _doc_id(item)
        if store.doc_exists(doc_id):
            skipped += 1
            continue
        text = f"{item.title}\n\n{item.content}"
        source_label = f"{item.source}:{item.url}" if item.url else item.source
        ingest_text(store, vectors, router, text=text, doc_id=doc_id, source=source_label, extract_kg=False)
        ingested += 1
        doc_ids.append(doc_id)

    store.log("system", "external_sync", {"ingested": ingested, "skipped_existing": skipped})
    return SyncResult(ingested=ingested, skipped_existing=skipped, doc_ids=doc_ids)
