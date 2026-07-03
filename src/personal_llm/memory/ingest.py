"""Ingest text/markdown/PDF -> chunk -> embed -> store (SQLite + Chroma) -> KG extraction."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from personal_llm.router import ModelRouter

from .store import MemoryStore
from .types import Chunk, MemoryRecord, new_id
from .vectors import VectorStore

_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_OVERLAP = 100


class IngestResult(BaseModel):
    doc_id: str
    chunks_ingested: int
    kg_triples: int = 0


def chunk_text(text: str, chunk_size: int = _DEFAULT_CHUNK_SIZE, overlap: int = _DEFAULT_OVERLAP) -> list[str]:
    """Simple sliding-window chunker over characters. Good enough for personal-scale notes."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def read_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        import pdfplumber

        parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
        return "\n".join(parts)
    return path.read_text(encoding="utf-8", errors="replace")


def ingest_text(
    store: MemoryStore,
    vectors: VectorStore,
    router: ModelRouter,
    *,
    text: str,
    doc_id: str,
    source: str,
    extract_kg: bool = True,
) -> IngestResult:
    pieces = chunk_text(text)
    if not pieces:
        return IngestResult(doc_id=doc_id, chunks_ingested=0)

    chunk_objs = [Chunk(id=new_id(), doc_id=doc_id, ord=i, text=piece) for i, piece in enumerate(pieces)]
    embeddings = router.embed([c.text for c in chunk_objs])

    ids, vecs, metadatas = [], [], []
    for chunk, vector in zip(chunk_objs, embeddings):
        chunk.vector_id = chunk.id
        store.add_chunk(chunk)
        store.add_memory(
            MemoryRecord(
                kind="semantic",
                content=chunk.text,
                source=source,
                vector_id=chunk.id,
                meta={"doc_id": doc_id, "chunk_id": chunk.id},
            )
        )
        ids.append(chunk.id)
        vecs.append(vector)
        metadatas.append({"chunk_id": chunk.id, "doc_id": doc_id})

    vectors.add(ids, vecs, metadatas)
    store.add_memory(
        MemoryRecord(
            kind="episodic",
            content=f"Ingested {source} ({len(chunk_objs)} chunks)",
            source=source,
            importance=0.4,
            meta={"doc_id": doc_id},
        )
    )
    store.log("system", "ingest", {"doc_id": doc_id, "source": source, "chunks": len(chunk_objs)})

    kg_triples = 0
    if extract_kg:
        from personal_llm.graph.kg import extract_and_store

        kg_triples = extract_and_store(store, router, chunk_objs)

    return IngestResult(doc_id=doc_id, chunks_ingested=len(chunk_objs), kg_triples=kg_triples)


def ingest_file(
    store: MemoryStore,
    vectors: VectorStore,
    router: ModelRouter,
    path: str | Path,
    extract_kg: bool = True,
) -> IngestResult:
    path = Path(path)
    text = read_file(path)
    doc_id = str(path.resolve())
    return ingest_text(store, vectors, router, text=text, doc_id=doc_id, source=str(path), extract_kg=extract_kg)
