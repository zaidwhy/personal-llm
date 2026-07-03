from personal_llm.memory.ingest import ingest_text
from personal_llm.memory.retrieve import semantic_search


def test_semantic_search_ranks_relevant_chunk_first(store, vectors, router):
    ingest_text(
        store, vectors, router,
        text="The cat sat on the mat. Cats are wonderful pets.",
        doc_id="doc-cat", source="notes/cat.md", extract_kg=False,
    )
    ingest_text(
        store, vectors, router,
        text="Quantum entanglement is a phenomenon studied in physics.",
        doc_id="doc-physics", source="notes/physics.md", extract_kg=False,
    )

    results = semantic_search(store, vectors, router, "Tell me about cats", k=5)

    assert results
    assert "cat" in results[0].text.lower()


def test_semantic_search_touches_memory_access_count(store, vectors, router):
    ingest_text(
        store, vectors, router,
        text="Zaid is building Personal LLM.",
        doc_id="doc-1", source="notes.md", extract_kg=False,
    )

    semantic_search(store, vectors, router, "What is Zaid building?", k=3)

    memories = store.list_memories(kind="semantic")
    assert any(m.access_count >= 1 for m in memories)


def test_semantic_search_empty_store_returns_empty(store, vectors, router):
    results = semantic_search(store, vectors, router, "anything", k=5)
    assert results == []
