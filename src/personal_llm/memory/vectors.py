"""Thin wrapper around Chroma - the only module that knows it's Chroma (ADR 0001)."""

from __future__ import annotations

from personal_llm.config import get_settings

_COLLECTION_NAME = "personal_llm_chunks"


class VectorStore:
    def __init__(self, persist_dir: str | None = None) -> None:
        import chromadb

        settings = get_settings()
        self._client = chromadb.PersistentClient(path=persist_dir or settings.personal_llm_chroma_dir)
        self._collection = self._client.get_or_create_collection(_COLLECTION_NAME)

    def add(self, ids: list[str], vectors: list[list[float]], metadatas: list[dict]) -> None:
        if not ids:
            return
        self._collection.add(ids=ids, embeddings=vectors, metadatas=metadatas)

    def query(self, vector: list[float], k: int = 8) -> list[tuple[str, float, dict]]:
        """Returns (id, similarity, metadata), similarity in [0, 1], highest first."""
        if self._collection.count() == 0:
            return []
        k = min(k, self._collection.count())
        result = self._collection.query(query_embeddings=[vector], n_results=k)
        ids = result["ids"][0]
        distances = result["distances"][0]
        metadatas = result["metadatas"][0]
        # Chroma default distance is squared L2 on normalized vectors; convert to a
        # bounded similarity score (1 = identical, 0 = dissimilar) for ranking.
        out = []
        for _id, dist, meta in zip(ids, distances, metadatas):
            similarity = max(0.0, 1.0 - dist / 2.0)
            out.append((_id, similarity, meta or {}))
        return out

    def count(self) -> int:
        return self._collection.count()
