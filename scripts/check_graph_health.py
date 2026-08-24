"""Report the entity-graph health numbers that Phase 0 step 5 is gated on.

The gate, from the NEXUS plan, is that the knowledge graph is a real graph rather than a
pile of duplicate rows. Before the deterministic-identity fix the live graph was 202
nodes / 101 edges / 101 connected components all of size 2, every node typed with the
literal string "entity", and "Personal LLM" stored 21 separate times - the signature of
`KGNode.id = uuid4().hex` plus `INSERT OR REPLACE`, which can never dedupe.

Thresholds checked here (all from the plan, none invented at report time):
  entities <= 80, "Personal LLM" resolves to exactly 1, largest connected component
  >= 10 nodes, and more than one distinct node type exists.

--verify-idempotent additionally re-applies the cached extraction over every chunk
WITHOUT wiping the graph first, and asserts the node and edge counts do not move. That is
the check the whole step exists for: today re-ingesting the same corpus doubled the
counts. It uses the cache written by rebuild_entities.py so that it measures identity,
not the LLM's run-to-run phrasing consistency.

Usage:
  python scripts/check_graph_health.py
  python scripts/check_graph_health.py --verify-idempotent
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from personal_llm.config import get_settings  # noqa: E402
from personal_llm.graph.kg import Triple, store_triples  # noqa: E402
from personal_llm.memory.identity import normalize_canonical_key  # noqa: E402
from personal_llm.memory.store import MemoryStore  # noqa: E402

MAX_ENTITIES = 80
MIN_LARGEST_COMPONENT = 10
_CACHE_FILENAME = "kg_extraction_cache.json"


def components(node_ids: list[str], edges: list[tuple[str, str]]) -> list[int]:
    """Sizes of the undirected connected components, largest first. Isolated nodes count
    as components of size 1 so the distribution is not silently flattering."""
    adjacency: dict[str, set[str]] = {nid: set() for nid in node_ids}
    for src, dst in edges:
        if src in adjacency and dst in adjacency:
            adjacency[src].add(dst)
            adjacency[dst].add(src)

    seen: set[str] = set()
    sizes = []
    for start in node_ids:
        if start in seen:
            continue
        size = 0
        queue = deque([start])
        seen.add(start)
        while queue:
            current = queue.popleft()
            size += 1
            for neighbour in adjacency[current]:
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        sizes.append(size)
    return sorted(sizes, reverse=True)


def report(store: MemoryStore) -> bool:
    nodes = store.all_nodes()
    edges = store.all_edges()
    node_ids = [n.id for n in nodes]
    sizes = components(node_ids, [(e.src, e.dst) for e in edges])
    types = Counter(n.type for n in nodes)
    relations = Counter(e.rel for e in edges)

    target_key = normalize_canonical_key("Personal LLM")
    personal_llm_rows = [n for n in nodes if n.canonical_key == target_key]

    largest = sizes[0] if sizes else 0
    print(f"entities:            {len(nodes)}  (gate: <= {MAX_ENTITIES})")
    print(f"edges:               {len(edges)}")
    print(f"components:          {len(sizes)}  sizes {sizes[:8]}{' ...' if len(sizes) > 8 else ''}")
    print(f"largest component:   {largest}  (gate: >= {MIN_LARGEST_COMPONENT})")
    print(f"'Personal LLM' rows: {len(personal_llm_rows)}  (gate: exactly 1)")
    print(f"node types ({len(types)}):      {dict(types)}  (gate: > 1)")
    print(f"relations ({len(relations)}):       {dict(relations)}")

    checks = {
        f"entities <= {MAX_ENTITIES}": len(nodes) <= MAX_ENTITIES,
        "'Personal LLM' == 1 row": len(personal_llm_rows) == 1,
        f"largest component >= {MIN_LARGEST_COMPONENT}": largest >= MIN_LARGEST_COMPONENT,
        "more than one node type": len(types) > 1,
    }
    print()
    for label, ok in checks.items():
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return all(checks.values())


def verify_idempotent(store: MemoryStore) -> bool:
    settings = get_settings()
    cache_path = settings.data_root / _CACHE_FILENAME
    if not cache_path.exists():
        print(f"\nno extraction cache at {cache_path} - run rebuild_entities.py --apply first")
        return False

    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    chunks = store.all_chunks()
    before = store.stats()

    reapplied = 0
    for chunk in chunks:
        cached = cache.get(chunk.id)
        if cached is None:
            continue
        triples = [Triple(**t) for t in cached["triples"]]
        reapplied += store_triples(store, chunk, triples)

    # merge_subsumed_people is part of ingest, not a one-off cleanup: rebuild_entities.py
    # runs it after storing, so "re-running ingest" means storing AND merging. Re-applying
    # only the store half recreates the short person name that the merge had folded away,
    # which showed up as +1 node and +19 edges - an artifact of testing half the pipeline,
    # not a failure of identity. The property that matters is that the whole pipeline is a
    # fixed point: run it again on the same corpus and nothing moves.
    store.merge_subsumed_people()

    after = store.stats()
    unchanged = before["kg_nodes"] == after["kg_nodes"] and before["kg_edges"] == after["kg_edges"]
    print(f"\nre-applied {reapplied} triples over {len(chunks)} chunks without wiping the graph")
    print(f"  nodes: {before['kg_nodes']} -> {after['kg_nodes']}")
    print(f"  edges: {before['kg_edges']} -> {after['kg_edges']}")
    print(f"  [{'PASS' if unchanged else 'FAIL'}] re-ingest is idempotent")
    return unchanged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--verify-idempotent", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    store = MemoryStore(settings.personal_llm_db_path)
    print(f"DB: {settings.personal_llm_db_path}\n")

    ok = report(store)
    if args.verify_idempotent:
        ok = verify_idempotent(store) and ok

    print(f"\n{'ALL CHECKS PASS' if ok else 'GATE NOT MET'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
