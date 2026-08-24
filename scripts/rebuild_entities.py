"""Rebuild the knowledge graph (nodes/edges/entity_aliases) from the merged chunks
table, using the deterministic identity rules in personal_llm.memory.identity instead
of the old uuid4-id / INSERT-OR-REPLACE behavior that let every mention of the same
entity become a fresh node.

Before this script: 202 nodes, 101 edges, 101 connected components all of size 2 (max
degree 1), "Personal LLM" stored as 21 separate nodes, every node's type the literal
string "entity". Those numbers came from extract_and_store running with a random id per
mention - the graph was never actually a graph, just 101 disconnected pairs.

This script deletes the existing nodes/edges/entity_aliases tables (their content is
derived data - reproducible from the chunks table, not a source of truth) and re-runs
triple extraction over every chunk with the fixed identity rules, so repeated mentions
of the same entity converge on one row and the graph gets real connectivity.

Extraction is cached per (chunk_id, text) in data/kg_extraction_cache.json. This matters
for the idempotency check the whole rebuild exists to satisfy: identity (upsert_entity,
deterministic ids) is provably idempotent given the SAME triples, but a live LLM is not
guaranteed to phrase entities identically across two separate calls, which would make a
naive "run the LLM twice" test conflate LLM sampling noise with an identity bug. Caching
extraction means re-running this script over an unchanged corpus reuses the exact same
triples and so isolates the actual thing being tested: does re-applying the same
extraction leave the node/edge count unchanged. Pass --no-cache to force fresh LLM calls.

--dry-run is the default: prints how many chunks would be processed and the current
graph counts, without calling the LLM or touching any table. --apply does the rebuild
for real (needs a working Gemini key or Ollama - see `doctor`).

Usage:
  python scripts/rebuild_entities.py                       # dry run
  python scripts/rebuild_entities.py --apply                # rebuild for real (cached)
  python scripts/rebuild_entities.py --apply --no-cache      # force fresh LLM calls
  python scripts/rebuild_entities.py --apply --provider ollama
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from personal_llm.config import get_settings  # noqa: E402
from personal_llm.graph.kg import Triple, extract_triples_strict, store_triples  # noqa: E402
from personal_llm.memory.store import MemoryStore  # noqa: E402
from personal_llm.memory.types import Chunk  # noqa: E402
from personal_llm.router.providers import GeminiProvider, OllamaProvider  # noqa: E402
from personal_llm.router.router import ModelRouter, RouterError  # noqa: E402

_CACHE_FILENAME = "kg_extraction_cache.json"


def _build_router(provider: str) -> ModelRouter:
    if provider == "gemini":
        return ModelRouter(chat_providers=[GeminiProvider()])
    if provider == "ollama":
        return ModelRouter(chat_providers=[OllamaProvider()])
    return ModelRouter()  # auto: prefers Ollama if healthy, else Gemini


def _text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def _load_cache(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_cache(path: Path, cache: dict) -> None:
    """Merge onto whatever is already on disk rather than replacing it. A --no-cache run
    starts from an empty dict in memory, so writing that dict out directly would delete
    every chunk it did not happen to re-extract - which is how a run that covered fewer
    chunks than the last one silently destroyed the good cache."""
    merged = _load_cache(path)
    merged.update(cache)
    path.write_text(json.dumps(merged, indent=2), encoding="utf-8")


def _triples_for_chunk(
    router: ModelRouter, chunk: Chunk, cache: dict, use_cache: bool, throttle: float = 0.0
) -> tuple[list[Triple], bool]:
    """Returns (triples, was_cache_hit)."""
    text_hash = _text_hash(chunk.text)
    cached = cache.get(chunk.id)
    if use_cache and cached is not None and cached["text_sha1"] == text_hash:
        return [Triple(**t) for t in cached["triples"]], True

    # Sleep before the call, not after, and only on a cache miss - a cached chunk costs
    # no request and must not be paced as though it did.
    if throttle:
        time.sleep(throttle)
    triples = extract_triples_strict(router, chunk.text)
    cache[chunk.id] = {"text_sha1": text_hash, "triples": [t.model_dump() for t in triples]}
    return triples, False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually rebuild the graph. Default is dry-run.")
    parser.add_argument(
        "--provider",
        choices=["auto", "gemini", "ollama"],
        default="gemini",
        help=(
            "Which chat provider extracts triples when the cache misses. Default "
            "'gemini' for naming consistency across mentions; 'auto' uses the router's "
            "normal local-first preference; 'ollama' forces local only."
        ),
    )
    parser.add_argument(
        "--no-cache", action="store_true", help="Ignore data/kg_extraction_cache.json and call the LLM for every chunk."
    )
    parser.add_argument(
        "--throttle",
        type=float,
        default=7.0,
        help=(
            "Seconds to wait before each uncached LLM call. Default 7: Gemini's free tier "
            "allows 10 requests per MINUTE (not per day), and the router's 3 fast retries "
            "burn through that window rather than waiting it out - which is what made a "
            "full run return zero triples for every chunk. Pass 0 for a local provider."
        ),
    )
    args = parser.parse_args()

    settings = get_settings()
    store = MemoryStore(settings.personal_llm_db_path)
    chunks = store.all_chunks()
    cache_path = settings.data_root / _CACHE_FILENAME

    before = store.stats()
    print(f"DB: {settings.personal_llm_db_path}")
    print(f"chunks available: {len(chunks)}")
    print(f"current graph: {before['kg_nodes']} nodes, {before['kg_edges']} edges")

    if not args.apply:
        print("\nDry run only - not calling the LLM or touching the graph. Re-run with --apply.")
        return 0

    router = _build_router(args.provider)
    cache = {} if args.no_cache else _load_cache(cache_path)
    print(f"\nProvider: {args.provider} (cache: {'disabled' if args.no_cache else cache_path})")

    # Extract everything BEFORE touching the graph. The wipe used to come first, so a
    # provider outage part-way through left the graph empty with nothing to restore it
    # from. Extraction is the only step that can fail; the store half cannot, so doing
    # it all up front means a failed run leaves the previous graph exactly as it was.
    print(f"Extracting triples from {len(chunks)} chunks (graph untouched until this succeeds)...")
    extracted: list[tuple[Chunk, list[Triple]]] = []
    cache_hits = 0
    try:
        for i, chunk in enumerate(chunks, 1):
            triples, hit = _triples_for_chunk(
                router, chunk, cache, use_cache=not args.no_cache, throttle=args.throttle
            )
            cache_hits += int(hit)
            extracted.append((chunk, triples))
            print(f"  [{i}/{len(chunks)}] {'(cached) ' if hit else ''}{chunk.doc_id} - {len(triples)} triples")
    except RouterError as exc:
        # Persist what did succeed, so the calls already paid for are not lost, then stop
        # loudly. Returning quietly here would look identical to a corpus with no triples.
        _save_cache(cache_path, cache)
        print(f"\nEXTRACTION FAILED after {len(extracted)}/{len(chunks)} chunks: {exc}")
        print("Graph left untouched. Partial extraction cached; re-run to resume.")
        return 1

    # Only persist once the whole corpus extracted cleanly. _save_cache merges, so this
    # is additive even after a --no-cache run.
    _save_cache(cache_path, cache)

    print("\nWiping existing nodes/edges/entity_aliases (derived data, reproducible from chunks)...")
    store.clear_graph()
    total_triples = 0
    for chunk, triples in extracted:
        total_triples += store_triples(store, chunk, triples)

    folded = store.merge_subsumed_people()
    print()
    print(f"Folded {folded} short person name(s) into their full name (kept as aliases)")

    after = store.stats()
    print(f"\nDone: {total_triples} triples extracted ({cache_hits}/{len(chunks)} chunks from cache)")
    print(f"-> {after['kg_nodes']} nodes, {after['kg_edges']} edges")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
