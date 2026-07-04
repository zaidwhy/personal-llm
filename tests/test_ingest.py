from pathlib import Path

from personal_llm.memory.ingest import chunk_text, ingest_text, read_file


def test_chunk_text_short_text_single_chunk():
    chunks = chunk_text("short text", chunk_size=800, overlap=100)
    assert chunks == ["short text"]


def test_chunk_text_empty_returns_empty():
    assert chunk_text("   ") == []


def test_chunk_text_splits_long_text_with_overlap():
    text = "a" * 2500
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) == 3
    assert all(len(c) <= 1000 for c in chunks)


def test_ingest_text_stores_chunks_and_memories(store, vectors, router):
    result = ingest_text(
        store, vectors, router,
        text="Personal LLM is a local-first memory engine.",
        doc_id="doc-1", source="notes.md", extract_kg=False,
    )

    assert result.chunks_ingested == 1
    assert result.kg_triples == 0
    assert vectors.count() == 1
    semantic = store.list_memories(kind="semantic")
    episodic = store.list_memories(kind="episodic")
    assert len(semantic) == 1
    assert len(episodic) == 1


def test_ingest_text_empty_text_ingests_nothing(store, vectors, router):
    result = ingest_text(store, vectors, router, text="   ", doc_id="doc-empty", source="notes.md")
    assert result.chunks_ingested == 0
    assert vectors.count() == 0


def test_read_file_routes_images_through_ocr(monkeypatch, tmp_path):
    monkeypatch.setattr("personal_llm.vision.ocr.extract_text_from_image", lambda path: "text from image")
    image_path = tmp_path / "screenshot.png"
    image_path.write_bytes(b"not-a-real-png")

    result = read_file(image_path)

    assert result == "text from image"


def test_read_file_reads_plain_text_normally(tmp_path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")

    assert read_file(Path(path)) == "hello"
