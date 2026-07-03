from personal_llm.graph.kg import ExtractedTriples, Triple, extract_and_store, related_entities
from personal_llm.memory.types import Chunk
from personal_llm.router.providers import RouterError
from personal_llm.router.schemas import Completion


class _KGRouter:
    """Stub chat provider that returns a canned triple - never calls a real model."""

    def embed(self, texts):
        return [[0.0] for _ in texts]

    def complete(self, messages, schema=None):
        parsed = ExtractedTriples(triples=[Triple(subject="Zaid", relation="builds", object="Personal LLM")])
        return Completion(text="", parsed=parsed, provider="fake", model="fake")


class _FailingRouter:
    def embed(self, texts):
        return [[0.0] for _ in texts]

    def complete(self, messages, schema=None):
        raise RouterError("boom")


def test_extract_and_store_creates_nodes_and_edges(store):
    chunk = Chunk(doc_id="doc-1", ord=0, text="Zaid builds Personal LLM.")

    count = extract_and_store(store, _KGRouter(), [chunk])

    assert count == 1
    assert {n.name for n in store.all_nodes()} == {"Zaid", "Personal LLM"}
    assert store.all_edges()[0].rel == "builds"


def test_related_entities_finds_one_hop_neighbor(store):
    chunk = Chunk(doc_id="doc-1", ord=0, text="Zaid builds Personal LLM.")
    extract_and_store(store, _KGRouter(), [chunk])

    related = related_entities(store, "Zaid", hops=1)

    assert any(r["name"] == "Personal LLM" for r in related)


def test_related_entities_unknown_name_returns_empty(store):
    assert related_entities(store, "Nobody") == []


def test_extract_triples_is_never_fatal_on_router_error(store):
    chunk = Chunk(doc_id="doc-1", ord=0, text="anything")

    count = extract_and_store(store, _FailingRouter(), [chunk])

    assert count == 0
