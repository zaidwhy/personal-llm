from personal_llm.memory.ingest import ingest_text
from personal_llm.rag.pipeline import NOT_IN_MEMORY, ask


def test_ask_returns_grounded_answer_with_sources(store, vectors, router):
    ingest_text(
        store, vectors, router,
        text="Zaid is building Personal LLM, a local-first memory engine.",
        doc_id="doc-1", source="notes.md", extract_kg=False,
    )

    answer = ask(store, vectors, router, "What is Zaid building?")

    assert answer.grounded is True
    assert answer.text == router.canned_text
    assert len(answer.sources) >= 1
    assert answer.sources[0].source == "notes.md"


def test_ask_returns_not_in_memory_for_unrelated_question(store, vectors, router):
    ingest_text(
        store, vectors, router,
        text="Zaid is building Personal LLM.",
        doc_id="doc-1", source="notes.md", extract_kg=False,
    )

    answer = ask(store, vectors, router, "boiling point tungsten vacuum experiment reading")

    assert answer.grounded is False
    assert answer.text == NOT_IN_MEMORY
    assert answer.sources == []


def test_ask_on_empty_memory_returns_not_in_memory(store, vectors, router):
    answer = ask(store, vectors, router, "anything at all")

    assert answer.grounded is False
    assert answer.text == NOT_IN_MEMORY
