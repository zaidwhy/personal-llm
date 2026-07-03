# Personal LLM - Technical Design Document

Companion to `PRD.md` (requirements/priorities) and `ARCHITECTURE.md` (diagrams/schemas). This document explains *how* each subsystem works.

---

## 1. Memory Architecture

Rather than building six separate memory "systems," v0.1 maps the classic cognitive-memory taxonomy onto three concrete stores, because that is what is actually implementable and testable:

| Cognitive concept | Implementation |
|---|---|
| **Working memory** | The current conversation/session context window - not persisted, lives in the caller's process. |
| **Episodic memory** | `memories` table in SQLite, `kind='episodic'` - timestamped events ("ingested file X", "user asked about Y"). |
| **Semantic memory** | `memories` table, `kind='fact'`/`kind='semantic'` + a matching vector in Chroma for similarity search. |
| **Procedural memory** | `memories` table, `kind='procedural'` - reusable "recipes" (e.g. prompt templates, user preferences like "always suggest 3 options"). Retrieved same as semantic memory but weighted differently. |
| **Vector memory** | Chroma collection, one entry per chunk, `vector_id` foreign key from `chunks`/`memories`. |
| **Long-term memory** | The persistent union of all of the above - SQLite + Chroma on disk. |

**Importance scoring:** each memory has an `importance` float (0-1), initialized by a heuristic (explicit user statements > ingested documents > incidental chat) and boostable by access frequency. Formula for retrieval ranking:

```
rank_score = 0.6 * cosine_similarity + 0.2 * importance + 0.2 * recency_decay
recency_decay = exp(-days_since_last_access / HALF_LIFE_DAYS)   # HALF_LIFE_DAYS default = 30
```

**Memory decay:** a scheduled `consolidate` job (run via CLI, later via a scheduler) lowers `importance` for memories not accessed in N days, and can soft-delete (mark `archived=true`, never hard-delete without user confirmation) memories below a floor threshold after a long period.

**Conflict resolution (P1):** when two semantic memories contradict (detected via LLM comparison during consolidation), both are kept but flagged (`meta.conflict_with = <id>`); retrieval surfaces the conflict rather than silently picking one - the user resolves it explicitly (P1, stubbed interface in v0.1).

**Memory editing/search (P1):** CLI `recall` command already supports search in v0.1; explicit edit/delete commands land in v0.2 once the audit log exists to track the change.

---

## 2. Knowledge Graph Design

v0.1 KG is intentionally "lite": no dedicated graph database yet (avoids standing up Neo4j for a personal-scale graph that will have thousands, not billions, of edges).

- **Extraction:** after ingest, an LLM call over each chunk extracts `(entity, relation, entity)` triples using a structured Pydantic schema (`ExtractedTriple`), same call pattern as `analyzer.py`'s structured outputs.
- **Storage:** `nodes(id, type, name, meta)` and `edges(src, rel, dst, weight, meta)` in the same SQLite file.
- **Traversal:** `networkx.DiGraph` built on demand from the SQLite tables for 1-hop/2-hop queries (e.g. "what else relates to X") to enrich RAG context.
- **Evolution path:** if the graph grows past ~100k edges or needs Cypher-style queries, swap in Kùzu (embedded, no server) behind the same `graph/kg.py` interface - documented as an ADR, not built now.

---

## 3. Reasoning Engine

Rejecting the brief's implication of six separate "reasoning engines" as separate systems (see PRD 4.2) - that is not how capability actually works in 2026 LLMs. Instead:

- **One strong general model** (via the router) handles all reasoning; *prompting strategy* differs by task (a "reasoning mode" is a system-prompt + schema choice, e.g. `_ANALYSIS_SYSTEM` in `analyzer.py`).
- **Verification pass (P1):** for high-stakes answers, a second call asks the model to critique its own answer against the retrieved sources before returning it ("does this answer contradict any retrieved fact?").
- **Uncertainty estimation (P0):** retrieval confidence (top similarity score) below a threshold triggers an explicit "I don't have this in memory" response instead of letting the model guess - implemented in `rag/pipeline.py`.
- **Hypothesis generation / decision trees (P2):** deferred until an agent actually needs multi-path planning (v0.2 agent framework); building it speculatively now would be premature abstraction.

---

## 4. Model Router

Single interface, two initial providers, designed for hybrid local+cloud per the locked decision:

```python
class ModelRouter:
    def complete(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Completion: ...
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

**Selection logic (v0.1):**
- `embed()` always uses the local `sentence-transformers` model - free, offline, no provider needed for ingest/retrieve to work at all.
- `complete()` tries Ollama first **only if** `OLLAMA_HOST` is configured and reachable (health-checked once, cached); otherwise falls back to Gemini. This satisfies "hybrid local+cloud" without making Ollama a hard dependency (most users, including Zaid today, won't have it running).
- Retry/backoff on 429/5xx reuses the exact pattern from `resume-job-fit-ai/analyzer.py:_generate` (3 attempts, 4s/8s backoff).

**Confidence & disagreement (P1):** when both providers are configured, an optional "verify" mode calls both and flags disagreement rather than silently picking one. Not built in v0.1 (no second provider running by default).

---

## 5. Agent Framework (P1, design now, build v0.2)

- **`Agent` base class:** `name`, `system_prompt`, `tools: list[Tool]`, `memory_scope` (which memory kinds it can read/write), `permissions` (which tools it may call without confirmation).
- **Loop:** plan -> select tool -> call tool (typed in/out, audited) -> observe result -> continue or answer. A bounded step count prevents runaway loops.
- **Specialization = configuration:** a "Research Agent" and a "Coding Agent" are the same `Agent` class instantiated with different prompts/tools/memory scopes - not separate codebases, directly satisfying the "engine, not app" principle.
- **Failure recovery:** tool call exceptions are caught, logged to `audit`, and surfaced to the agent as an observation ("tool X failed: ...") so it can retry or give up gracefully rather than crashing.
- **Priority/conflict (P2):** only relevant once multiple agents run concurrently; not designed further until v0.2 ships a single working agent.

---

## 6. Tool Integration Layer (P1)

- Every tool is a typed function: Pydantic input schema, Pydantic output schema, a `permission_level` (`read_only` / `write` / `sensitive`).
- Tool calls always go through one dispatcher that logs to `audit(actor, action, detail)` before and after execution - nothing is silent.
- v0.2 ships 2-3 safe tools: local file read, memory query (wraps `memory/retrieve.py`), and (if available) a web-search MCP tool already in this environment.
- **Prompt injection defense:** content retrieved from tools/ingested documents is wrapped in an explicit `<untrusted_content>` tag in prompts and the system prompt instructs the model never to treat tagged content as instructions - simple, documented, and enforced from the first tool, not bolted on later.

---

## 7. Security & Privacy

| Concern | Mitigation |
|---|---|
| Data exfiltration | Local-first storage; only explicit `complete()`/`embed()` calls leave the device, and only to the configured provider. |
| Secrets | `.env`, never committed; `.env.example` documents shape only (per user's existing `.env` policy). |
| Prompt injection | Untrusted-content tagging (above); tool outputs never auto-executed as instructions. |
| Tool misuse | Permission levels + audit log; sensitive tools require explicit confirmation (v0.2). |
| At-rest encryption (P1) | SQLite file can be placed on an encrypted volume; app-level encryption of the `content` column is a documented future option (ADR), not built in v0.1 since it complicates search without a clear near-term need. |
| Model verification | Structured-output schemas (Pydantic) reject malformed responses at the boundary, same as `analyzer.py`. |

---

## 8. API Specification (v0.1 FastAPI surface)

| Method | Path | Purpose |
|---|---|---|
| POST | `/ingest` | Ingest raw text or a file path into memory |
| POST | `/ask` | RAG question -> grounded answer + sources |
| POST | `/memory/remember` | Store an explicit fact/preference |
| GET | `/memory/recall?q=...` | Semantic search over memory |
| GET | `/stats` | Memory/graph counts, health |

Request/response bodies are the same Pydantic models used internally (`MemoryRecord`, `Completion`, etc.) - no separate "API schema" to keep in sync.

## 9. SDK Design

The SDK **is** the Python package: `pip install -e .` inside another project's venv (or a local path dependency) gives `from personal_llm.memory import MemoryStore`, `from personal_llm.rag import ask`. No separate SDK layer is built for v0.1 - premature given exactly one consumer (Zaid's other projects) exists today. A documented FastAPI surface (above) covers non-Python callers.

## 10. Database Schemas

See `ARCHITECTURE.md` for the full DDL. Summary: `memories`, `chunks`, `nodes`, `edges`, `audit` - all in one SQLite file at `data/personal_llm.db`; vectors live in a parallel Chroma collection at `data/chroma/`, linked by `vector_id`.

## 11. Scalability Plan

Personal-scale first: SQLite + Chroma comfortably handle tens of thousands of memories/chunks on a laptop. If this ever needs to scale beyond one user's personal data (e.g. a multi-user product), the migration path is: SQLite -> Postgres, Chroma -> a managed vector DB (Qdrant/pgvector), NetworkX -> Kùzu/Neo4j - each swap isolated behind the existing module boundaries (`memory/store.py`, `memory/vectors.py`, `graph/kg.py`), so the rest of the engine doesn't change.

## 12. Research Challenges (honest list)

- Reliable long-horizon memory consolidation without losing nuance (open research problem industry-wide, not solved here - v0.1 uses simple heuristics, not claimed to be optimal).
- Conflict resolution between contradicting memories without user annotation is genuinely hard; v0.1 flags rather than auto-resolves.
- Prompt injection defense is best-effort tagging, not a solved problem; do not treat it as a security boundary for truly sensitive tools.

## 13. Risk Assessment

See `ROADMAP.md` risk table - duplicated there for visibility alongside the phased plan.
