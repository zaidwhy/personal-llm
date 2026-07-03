# Personal LLM - System Architecture Blueprint

## System Diagram

```
                 +-------------------- Interfaces --------------------+
                 |  Streamlit chat   |   Typer CLI   |  FastAPI /api  |
                 +---------------------------+------------------------+
                                             |  (one stable engine API)
                 +---------------------------v------------------------+
                 |                    PERSONAL LLM ENGINE             |
                 |                                                    |
   ask/ingest -> |  RAG pipeline  ->  Reasoning loop  ->  Agents(P1)  |
                 |       |                 |                |         |
                 |       v                 v                v         |
                 |   Retrieve         Model Router     Tool layer(P1) |
                 |   (rank)          (Gemini|Ollama)   (typed+audited)|
                 |       |                                            |
                 |  +----v-------------------- Memory ---------------+|
                 |  | episodic(SQLite) semantic/vector(Chroma)       ||
                 |  | procedural(recipes)  Knowledge Graph(SQLite)   ||
                 |  | importance scoring | decay | consolidation     ||
                 |  +------------------------------------------------+|
                 +----------------------------------------------------+
                        local-first data on device (encrypted opt.)
```

## Sequence Diagram - Ingest Flow

```
User -> CLI/API: ingest("notes.md")
CLI -> ingest.py: read + chunk(text)
ingest.py -> router.embed(chunks) -> [vectors]
ingest.py -> vectors.py (Chroma): add(vectors, ids)
ingest.py -> store.py (SQLite): insert chunks + memories(kind=episodic)
ingest.py -> kg.py: extract_triples(chunk) [LLM call, structured output]
kg.py -> store.py: insert nodes/edges
ingest.py -> store.py: insert audit(action="ingest")
ingest.py -> CLI: "Ingested N chunks from notes.md"
```

## Sequence Diagram - Ask (RAG) Flow

```
User -> CLI/API: ask("what did I decide about X?")
rag/pipeline.py -> retrieve.py: semantic_search(query, k=8)
retrieve.py -> vectors.py: query Chroma by embedding(query)
retrieve.py -> store.py: fetch memory rows for hit ids
retrieve.py -> pipeline: ranked chunks (similarity, importance, recency)
pipeline -> (if top_score < threshold): return "not in memory"
pipeline -> router.complete(system + grounded_context + question, schema=Answer)
router -> Gemini (or Ollama if configured/healthy)
router -> pipeline: Answer{text, cited_sources}
pipeline -> store.py: insert memories(kind=episodic, "asked: ...")
pipeline -> CLI/API: answer + sources
```

## Sequence Diagram - Agent + Tool Flow (P1, v0.2)

```
User -> Agent: task
Agent -> Router: plan next step
Agent -> ToolLayer: call tool(typed input)
ToolLayer -> store.py: audit(before)
ToolLayer -> Tool: execute
ToolLayer -> store.py: audit(after, result/error)
ToolLayer -> Agent: observation
Agent -> Router: next step or final answer
Agent -> User: result (+ audit trail available)
```

## Data Flow Diagram

```
Files/Notes/PDFs --ingest--> Chunks --embed--> Vectors (Chroma)
                                |                    |
                                +--extract KG-------> Nodes/Edges (SQLite)
                                |
                                +--metadata---------> memories table (SQLite)

Query --embed--> Chroma similarity search --rank(sim, importance, recency)--> Context
Context + Query --router.complete--> Grounded Answer + Sources --> User
                                              |
                                              +--log--> audit table
```

## Multi-Device / Sync Sketch (P2, not built in v0.1)

v0.1 is single-device (data lives in `./data/` on one machine). Future sync options, evaluated but not implemented:
1. **Manual**: sync `data/` via existing cloud storage (Drive/Dropbox) - zero code, works today if needed.
2. **Git-based**: version the SQLite file + a diffable export; risky for binary DB merges.
3. **Server-backed**: FastAPI service becomes a always-on host (e.g. home server), other devices are pure clients - the cleanest long-term path, deferred until there is a second device that actually needs it.

## Core Database Schema (SQLite, `data/personal_llm.db`)

```sql
CREATE TABLE memories (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,                 -- episodic | semantic | procedural | fact
  content TEXT NOT NULL,
  source TEXT,                        -- file path, "chat", "user", etc.
  importance REAL NOT NULL DEFAULT 0.5,
  last_accessed TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  vector_id TEXT,
  meta TEXT                           -- JSON blob
);

CREATE TABLE chunks (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  vector_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  meta TEXT
);

CREATE TABLE edges (
  src TEXT NOT NULL,
  rel TEXT NOT NULL,
  dst TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  meta TEXT,
  PRIMARY KEY (src, rel, dst)
);

CREATE TABLE audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,                -- "system" | "user" | agent name
  action TEXT NOT NULL,
  detail TEXT                         -- JSON blob
);

CREATE INDEX idx_memories_kind ON memories(kind);
CREATE INDEX idx_chunks_doc ON chunks(doc_id);
CREATE INDEX idx_edges_src ON edges(src);
CREATE INDEX idx_edges_dst ON edges(dst);
```

Chroma collection `personal_llm_chunks`: one entry per chunk, `id = chunk.vector_id`, metadata `{chunk_id, doc_id}`.

## Technology Stack Summary

See `docs/DECISIONS/` for the ADRs behind each choice; summarized in the main plan and `TDD.md` section 4/10.
