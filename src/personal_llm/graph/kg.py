"""Minimal knowledge graph: LLM triple extraction + SQLite storage + NetworkX traversal.

docs/TDD.md section 2 - deliberately "lite": no dedicated graph DB at personal scale.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from personal_llm.memory.identity import (
    classify_entity_type,
    is_valid_entity_name,
    normalize_canonical_key,
    normalize_relation,
)
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.types import Chunk, KGEdge, KGNode
from personal_llm.router import Message, ModelRouter
from personal_llm.router.router import RouterError

_SYSTEM = (
    "Extract factual (subject, relation, object) triples about clearly named, reusable "
    "entities - people, projects, tools, organizations, or places worth looking up again. "
    "Only extract clear, explicit relationships - do not invent facts. "
    "Skip commands, code snippets, file paths, and one-off descriptive phrases; they are "
    "not entities. Skip abstract qualities and generic nouns ('quality', 'craftsmanship', "
    "'vision', 'needs'), hardware specifications and version strings ('16 GB RAM', "
    "'RTX 3050', 'v2'), and anything you would not expect to look up again by name. "
    "A good subject or object is a proper name you could search for. "
    "Keep subject/object names SHORT (1-4 words) and in the same canonical form every "
    "time the same entity appears (e.g. always 'Zaid', never 'the user Zaid mentioned' or "
    "'Zaid Ali Syed, the developer'; always 'Personal LLM', never 'the Personal LLM system "
    "described in this README'). "
    "If there are no such relationships, return an empty list."
)


class Triple(BaseModel):
    subject: str
    relation: str
    object: str


class ExtractedTriples(BaseModel):
    triples: list[Triple] = Field(default_factory=list)


def extract_triples_strict(router: ModelRouter, text: str) -> list[Triple]:
    """Extract triples, letting a provider failure propagate as RouterError.

    Any caller that PERSISTS the result must use this rather than extract_triples: an
    empty list from a quota-exhausted provider is indistinguishable from a genuine
    "this chunk contains no triples", and writing the former down as the latter poisons
    the cache permanently. That is not hypothetical - it is exactly how one rebuild run
    emptied the graph and then saved 35 empty results over a good extraction cache.
    """
    messages = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=f"<context>\n{text}\n</context>"),
    ]
    completion = router.complete(messages, schema=ExtractedTriples)
    if isinstance(completion.parsed, ExtractedTriples):
        return completion.parsed.triples
    return []


def extract_triples(router: ModelRouter, text: str) -> list[Triple]:
    """Best-effort extraction for the live ingest path, where a missing graph edge is
    better than a failed ingest. Anything that writes the result down wants
    extract_triples_strict instead."""
    try:
        return extract_triples_strict(router, text)
    except RouterError:
        return []  # KG extraction is a bonus enrichment, never fatal to ingest


def _entity_node(name: str) -> KGNode:
    """type is classified deterministically from the normalized name, not asked of the
    LLM per mention - if type varied between two mentions of the same entity it would
    fragment one real-world entity across multiple (type, canonical_key) rows, since
    type is part of the identity key (see memory/identity.classify_entity_type)."""
    canonical_key = normalize_canonical_key(name)
    return KGNode(type=classify_entity_type(canonical_key), name=name, canonical_key=canonical_key)


def store_triples(store: MemoryStore, chunk: Chunk, triples: list[Triple]) -> int:
    """The storage half of extract_and_store, split out so a caller that wants to
    re-apply a previously extracted (and possibly cached) triple list - without calling
    the LLM again - can do so directly. Applying the same triples twice is what proves
    upsert_entity's idempotency against a live corpus, independent of whether the LLM
    itself would extract the exact same triples on a second call."""
    total = 0
    for triple in triples:
        if not (is_valid_entity_name(triple.subject) and is_valid_entity_name(triple.object)):
            continue  # blank, "null", a bare letter, or a whole clause - not a lookup-able entity
        subject_node = _entity_node(triple.subject)
        object_node = _entity_node(triple.object)
        store.upsert_entity(subject_node)
        store.upsert_entity(object_node)
        relation = normalize_relation(triple.relation)
        store.add_edge(
            KGEdge(
                src=subject_node.id,
                rel=relation,
                dst=object_node.id,
                meta={"chunk_id": chunk.id, "raw_relation": triple.relation},
            )
        )
        total += 1
    return total


def extract_and_store(store: MemoryStore, router: ModelRouter, chunks: list[Chunk]) -> int:
    total = 0
    for chunk in chunks:
        triples = extract_triples(router, chunk.text)
        total += store_triples(store, chunk, triples)
    return total


def build_graph(store: MemoryStore):
    import networkx as nx

    graph = nx.DiGraph()
    nodes_by_id = {n.id: n for n in store.all_nodes()}
    for node in nodes_by_id.values():
        graph.add_node(node.id, name=node.name, type=node.type)
    for edge in store.all_edges():
        graph.add_edge(edge.src, edge.dst, rel=edge.rel, weight=edge.weight)
    return graph, nodes_by_id


def related_entities(store: MemoryStore, name: str, hops: int = 1) -> list[dict]:
    """1-hop (default) neighbors of the node matching `name`, for enriching retrieval context."""
    graph, nodes_by_id = build_graph(store)
    matches = [nid for nid, n in nodes_by_id.items() if n.name.lower() == name.lower()]
    if not matches:
        return []
    results: list[dict] = []
    for start in matches:
        for neighbor_id in nx_neighbors_within_hops(graph, start, hops):
            if neighbor_id == start:
                continue
            neighbor = nodes_by_id.get(neighbor_id)
            if neighbor:
                results.append({"name": neighbor.name, "type": neighbor.type})
    return results


def nx_neighbors_within_hops(graph, start, hops: int) -> set[str]:
    import networkx as nx

    lengths = nx.single_source_shortest_path_length(graph.to_undirected(), start, cutoff=hops)
    return set(lengths.keys())
