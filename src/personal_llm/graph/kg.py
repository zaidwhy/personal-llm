"""Minimal knowledge graph: LLM triple extraction + SQLite storage + NetworkX traversal.

docs/TDD.md section 2 - deliberately "lite": no dedicated graph DB at personal scale.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from personal_llm.memory.store import MemoryStore
from personal_llm.memory.types import Chunk, KGEdge, KGNode
from personal_llm.router import Message, ModelRouter
from personal_llm.router.router import RouterError

_SYSTEM = (
    "Extract factual (subject, relation, object) triples from the given text. "
    "Only extract clear, explicit relationships - do not invent facts. "
    "Keep subject/object names short and consistent (e.g. 'Zaid', not 'the user Zaid mentioned'). "
    "If there are no clear relationships, return an empty list."
)


class Triple(BaseModel):
    subject: str
    relation: str
    object: str


class ExtractedTriples(BaseModel):
    triples: list[Triple] = Field(default_factory=list)


def extract_triples(router: ModelRouter, text: str) -> list[Triple]:
    messages = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=f"<context>\n{text}\n</context>"),
    ]
    try:
        completion = router.complete(messages, schema=ExtractedTriples)
    except RouterError:
        return []  # KG extraction is a bonus enrichment, never fatal to ingest
    if isinstance(completion.parsed, ExtractedTriples):
        return completion.parsed.triples
    return []


def extract_and_store(store: MemoryStore, router: ModelRouter, chunks: list[Chunk]) -> int:
    total = 0
    for chunk in chunks:
        for triple in extract_triples(router, chunk.text):
            subject_node = KGNode(type="entity", name=triple.subject)
            object_node = KGNode(type="entity", name=triple.object)
            store.add_node(subject_node)
            store.add_node(object_node)
            store.add_edge(
                KGEdge(src=subject_node.id, rel=triple.relation, dst=object_node.id, meta={"chunk_id": chunk.id})
            )
            total += 1
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
