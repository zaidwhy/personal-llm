# NEXUS - Phase 0 handoff

Last updated: 2026-08-24. **Phase 0 is complete. Phase 1 is stopped by Zaid's decision,
not blocked.**

## Status: Phase 0 done, Phase 1 not starting

All eight Phase 0 steps are finished and pushed. Phase 1 (the bitemporal world model,
prediction ledger, baselines and holdout harness) is **deliberately not being started.**

The reasoning, so it is not relitigated from memory later:

- Phase 0 was worth it on its own. It was debt paydown that found live defects in things
  Zaid actually uses - a knowledge graph that was never a graph, a Lumi client that had
  drifted from its own gateway on four points at once, and a `lumi.db` stamped v1 while
  the code was at v5.
- Phase 1's headline claim is weak even if it wins. "A model predicts which files I touch
  next better than a recency baseline" is not compelling to a recruiter and not novel to a
  researcher, and the holdout is 19 sessions.
- Its one genuinely novel piece, `conceivable@as_of`, is already demonstrated more
  strikingly in AUGUR, on vintage LLMs, replicated across two models.
- Opportunity cost: AUGUR and COLD READ both have real, replicated, unpublished findings.
  Those need writing up, not another multi-week build with pre-registered kill conditions
  that expect a null.

If Phase 1 is ever revived, the plan file is still the doc of record and everything below
still applies. Nothing here is abandoned mid-change.

## Where Phase 0 stands

| Step | State |
|---|---|
| 1. Merge `night-shift/2026-07-11` into master | done |
| 2. Fast-forward `ai-ecosystem` | done |
| 3. Absolute data paths (`NEXUS_DATA_DIR`) | done |
| 4. Merge the three diverged DBs | done |
| 5. Deterministic entity IDs | **done, one gate failing - see below** |
| 6. lumi `pllm.py` four mismatches | done, committed `a800417` (lumi has no remote) |
| 7. lumi `db.py` migration runner | done, same commit |
| 8. `recall/backend/memory.py` injectable | done, committed and pushed `0828664` |

Tests green in all three repos: personal-llm **168**, lumi **248**, recall **37**.

## Step 5 gate, as measured

Run it yourself:

```
python scripts/rebuild_entities.py --apply --provider ollama --throttle 0
python scripts/check_graph_health.py --verify-idempotent
```

```
PASS  re-ingest idempotent    205 nodes / 230 edges, unchanged on a second pass
PASS  "Personal LLM"          exactly 1 node (was 21)
PASS  largest component       135 (was 2)
PASS  node types              6 types, 6 relations (was 1 type, free-text relations)
PASS  no key split across types   0
FAIL  entities <= 80          205
```

Numbers are after re-extracting all 35 chunks with a single provider (llama3.1:8b), so
there is no mixed-provider confound.

### The count gate fails, and it should be replaced rather than met

Deduplication is provably perfect on this corpus, which is the property the count was
only ever a proxy for:

```
distinct canonical keys: 205 of 205 nodes     <- 1:1, zero duplication
keys split across types: 0
near-duplicate keys:     1   [('v2', 'v3')]   <- genuinely different, not a duplicate
```

205 nodes means 205 distinct entities. The corpus contains Zaid's full resume, so it
genuinely holds several hundred named things (CSS, Flask, Figma, GitHub, Machine
Learning, Chhatrapati Sambhajinagar). The 80 was pre-registered against a 202-node
baseline produced by a much smaller triple set, so it was never a like-for-like
comparison, and it scales with how much the extractor emits rather than with how well
identity resolves.

Recommendation, needing Zaid's sign-off: amend the plan to replace `entities <= 80` with
the duplication gate (distinct canonical keys == node count, and keys split across types
== 0). That measures the real property and does not move with corpus size.

`MAX_ENTITIES` has deliberately NOT been edited. The count check is still there and still
failing. Changing a pre-registered kill condition after seeing the number is exactly what
the plan's own kill condition #5 exists to prevent, so it stays visible until Zaid amends
it on purpose.

Single-provider extraction is also simply better: it moved the count 233 -> 205 and
produced richer relations, confirming that mixing Gemini and llama3.1 had inflated both.

## Gemini free tier - the trap that cost this session an hour

Two separate quotas, and the error message names whichever one you hit:

- `GenerateRequestsPerMinutePerProjectPerModel` - 10/min
- `GenerateRequestsPerDayPerProjectPerModel` - **20/day**

The router's 3 fast retries burn the per-minute window rather than waiting it out.
`rebuild_entities.py --throttle` (default 7s) handles the per-minute limit. Nothing
handles 20/day except using `--provider ollama`, which is free and unlimited and is what
the plan's local-first rule wants anyway.

Ollama self-upgrades on first launch and kills its own server doing it; wait roughly a
minute and poll `http://127.0.0.1:11434/api/tags` before assuming it is broken.

## Defects fixed along the way

All four were found by running the pipeline, not by reading it:

- `extract_triples` swallowed `RouterError` into `[]`, so a quota-exhausted provider was
  indistinguishable from a chunk with no triples. One run cached 35 empty results over a
  good cache and emptied the graph. `extract_triples_strict` is now the variant every
  caller that persists a result must use.
- `rebuild_entities.py` wiped the graph *before* extracting. It now extracts everything
  first and wipes only once that succeeds, and `_save_cache` merges onto disk instead of
  replacing it.
- `_fold_node_into` repointed edges with a plain `UPDATE`, hitting the UNIQUE constraint
  on `(src, rel, dst)` whenever the keeper already had the same edge, aborting the merge
  half-done.
- `normalize_canonical_key("analysis")` returned `"analysi"`.

## lumi - steps 6 and 7

Committed as `a800417` on Zaid's explicit go-ahead, which overrides lumi's standing
"Zaid commits" rule for this change. lumi has no git remote, so it is local-only by
design and there is nothing to push. 248 tests pass.

Step 6 fixed all four `pllm.py` mismatches together (`query=` vs `q=`, `.get("results")`
on a bare list in both the async and sync recall, and `remember()` posting `{text, tags}`
where the route takes `{fact, importance}`). They had to move together: the wrong
parameter name made the gateway answer 422 before any response handling ran, so fixing
only the parameter name would have converted a handled HTTP error into an uncaught
AttributeError inside session start.

`tests/test_pllm_contract.py` reads the gateway's real route signatures out of the
personal-llm checkout with `ast` and compares them against what the client puts on the
wire, so drift on either side fails. It parses rather than imports, because
`personal_llm.interfaces.api` pulls in chromadb and sentence-transformers which are
deliberately absent from lumi's venv. It skips cleanly when `PERSONAL_LLM_ROOT` is
missing. The tests were verified by deliberately regressing the client and confirming
they fail.

Step 7 replaced `db.py`'s `INSERT OR IGNORE` version stamp with a real migration runner.
The live `lumi.db` read version 1 while the code was at 5 - confirmed before the fix.
A database stamped newer than the code is refused rather than downgraded.

## Step 8 - recall, done

`recall/backend/memory.py` was a module singleton: paths computed at import time and an
`@lru_cache(maxsize=1)` collection handle, so only one store could exist per process, and
tests worked around it by monkeypatching globals and clearing the cache. `MemoryStore` now
owns its own paths and collection; the module-level functions stay as delegates to a cached
default store, because `backend/main.py` and `backend/tools.py` call them directly and
should not change for an internal refactor. `close()` releases the PersistentClient handle,
without which a `tmp_path` teardown raises WinError 32 on Windows.

Verified by the acceptance test the plan asks for: two stores against two directories,
written and read simultaneously, no monkeypatching, no cache clearing, each asserted to see
only its own data in both directions. 37 tests pass. Committed and pushed as `0828664`.

## If Phase 0 is ever re-verified

The exit gate as written: one DB, one Chroma dir, both absolute; tests green in all three
repos; `stats()` identical from any CWD. All hold. The only open item is the entity-count
threshold amendment described above, which is Zaid's call and not a build task.
