# NEXUS - Phase 0 handoff

Last updated: 2026-08-24, end of the Phase 0 steps 5-7 session.

## Where Phase 0 stands

| Step | State |
|---|---|
| 1. Merge `night-shift/2026-07-11` into master | done |
| 2. Fast-forward `ai-ecosystem` | done |
| 3. Absolute data paths (`NEXUS_DATA_DIR`) | done |
| 4. Merge the three diverged DBs | done |
| 5. Deterministic entity IDs | **done, one gate failing - see below** |
| 6. lumi `pllm.py` four mismatches | done, **uncommitted in lumi by policy** |
| 7. lumi `db.py` migration runner | done, **uncommitted in lumi by policy** |
| 8. `recall\backend\memory.py` injectable | **not started - next task** |

personal-llm is committed and pushed (`5e54982`, `master` clean against origin).
168 tests pass.

## Step 5 gate, as measured

Run it yourself:

```
python scripts/rebuild_entities.py --apply --provider ollama --throttle 0
python scripts/check_graph_health.py --verify-idempotent
```

```
PASS  re-ingest idempotent    233 nodes / 247 edges, unchanged on a second pass
PASS  "Personal LLM"          exactly 1 node (was 21)
PASS  largest component       149 (was 2)
PASS  node types              6 types, 5 relations (was 1 type, free-text relations)
FAIL  entities <= 80          233
```

The idempotency check is the one the step exists for, and it holds. The count gate
does not, and **the threshold has deliberately not been moved.**

### Why 233, and what would actually fix it

192 of the 233 nodes are typed `concept`. Inspecting them, most are real, distinct,
lookup-able entities - CSS, Flask, Figma, GitHub, Machine Learning, CivilizationOS,
Chhatrapati Sambhajinagar. The corpus includes Zaid's full resume and several "about
me" chunks, one of which alone yields 33 triples. The 80 was pre-registered against a
202-node baseline produced by a much smaller triple set, so it was never a like-for-like
comparison.

So this is an extraction-scope problem, not an identity problem. The options, in the
order I would try them:

1. Decide whether resume-style skill lists belong in the entity graph at all. A skills
   inventory is a list, not a graph, and it is what the count is made of.
2. Re-extract everything with one provider. The current graph is mixed: 21 chunks from
   Gemini, 14 from local llama3.1:8b after the Gemini free tier hit its 20-request daily
   cap. llama3.1 is visibly looser about what counts as an entity.
3. Only then consider tightening `is_valid_entity_name`. It already rejects blanks,
   nullish strings, single letters, clauses over 5 words, command-line flags and hardware
   quantities - all by shape, with no per-name blocklist, which is the property that keeps
   it honest.

Do not close this by editing `MAX_ENTITIES`.

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

## lumi - steps 6 and 7, done but NOT committed

`server/db.py`, `server/pllm.py`, `tests/test_db.py`, `tests/test_pllm.py`, and the new
`tests/test_pllm_contract.py` are modified in the working tree. 248 tests pass.

They are uncommitted on purpose: lumi's own `CLAUDE.md` line 75 says *"Do not commit from
this build track - Sonnet builds, Opus reviews at gates, Zaid commits."* The work is
finished and green; it needs Zaid's commit, not more building.

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

## Next task

Phase 0 step 8: make `recall\backend\memory.py` injectable (module path constants plus an
`lru_cache` singleton), verified by standing up two independent stores in one process.

Then the Phase 0 exit gate: one DB, one Chroma dir, both absolute; tests green in all
three repos; `stats()` identical from any CWD. The entity-count question above is the
only thing still open, and it is a scoping decision for Zaid, not a build task.
