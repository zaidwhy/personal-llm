from personal_llm.memory.types import Chunk, KGEdge, KGNode, MemoryRecord


def test_add_and_get_memory(store):
    record = MemoryRecord(kind="fact", content="Zaid prefers concise answers.", source="user")
    store.add_memory(record)

    fetched = store.get_memory(record.id)
    assert fetched is not None
    assert fetched.content == "Zaid prefers concise answers."
    assert fetched.kind == "fact"
    assert fetched.archived is False


def test_list_memories_filters_kind_and_archived(store):
    a = MemoryRecord(kind="fact", content="fact one")
    b = MemoryRecord(kind="episodic", content="event one")
    store.add_memory(a)
    store.add_memory(b)
    store.archive_memory(a.id)

    facts = store.list_memories(kind="fact")
    assert facts == []  # archived, excluded by default

    all_facts = store.list_memories(kind="fact", include_archived=True)
    assert len(all_facts) == 1

    episodic = store.list_memories(kind="episodic")
    assert len(episodic) == 1
    assert episodic[0].content == "event one"


def test_touch_memory_bumps_access(store):
    record = MemoryRecord(kind="fact", content="touch me")
    store.add_memory(record)
    store.touch_memory(record.id)
    store.touch_memory(record.id)

    fetched = store.get_memory(record.id)
    assert fetched.access_count == 2
    assert fetched.last_accessed is not None


def test_set_importance_and_update_meta(store):
    record = MemoryRecord(kind="fact", content="importance test", importance=0.5)
    store.add_memory(record)

    store.set_importance(record.id, 0.9)
    store.update_meta(record.id, {"tag": "important"})

    fetched = store.get_memory(record.id)
    assert fetched.importance == 0.9
    assert fetched.meta == {"tag": "important"}


def test_get_memories_by_vector_ids(store):
    record = MemoryRecord(kind="semantic", content="chunked content", vector_id="vec-123")
    store.add_memory(record)

    found = store.get_memories_by_vector_ids(["vec-123", "nonexistent"])
    assert "vec-123" in found
    assert "nonexistent" not in found
    assert found["vec-123"].content == "chunked content"


def test_chunks_roundtrip(store):
    chunk = Chunk(doc_id="doc-1", ord=0, text="hello world", vector_id="v1")
    store.add_chunk(chunk)

    fetched = store.get_chunks([chunk.id])
    assert len(fetched) == 1
    assert fetched[0].text == "hello world"
    assert fetched[0].doc_id == "doc-1"


def test_kg_nodes_and_edges(store):
    n1 = KGNode(type="entity", name="Zaid")
    n2 = KGNode(type="entity", name="Personal LLM")
    store.add_node(n1)
    store.add_node(n2)
    store.add_edge(KGEdge(src=n1.id, rel="builds", dst=n2.id))

    nodes = store.all_nodes()
    edges = store.all_edges()
    assert {n.name for n in nodes} == {"Zaid", "Personal LLM"}
    assert len(edges) == 1
    assert edges[0].rel == "builds"


def test_audit_log(store):
    store.log("system", "ingest", {"doc_id": "doc-1"})
    # no public getter for audit yet - verify it doesn't raise and stats stay consistent
    assert store.stats()["memories"] == 0


def test_stats_counts(store):
    store.add_memory(MemoryRecord(kind="fact", content="a"))
    store.add_memory(MemoryRecord(kind="episodic", content="b"))
    stats = store.stats()
    assert stats["memories"] == 2
    assert stats["memories_by_kind"]["fact"] == 1
    assert stats["memories_by_kind"]["episodic"] == 1
