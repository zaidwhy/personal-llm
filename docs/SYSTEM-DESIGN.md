# System design

System-design case study for personal-llm. `docs/ARCHITECTURE.md` covers the diagrams
(sequence/data-flow); this document covers the design decisions and tradeoffs behind them.

## Problem

Build one memory-and-retrieval kernel once, import it everywhere, instead of rebuilding
ingest/retrieve/generate for every new AI project. The kernel has to work with zero API
key at all for retrieval (a demo visitor, or CI, should never need to pay to prove it
retrieves correctly), answer only from what it actually retrieved, and say so honestly
when nothing relevant is in memory rather than guessing.

## Requirements

- Ingest arbitrary text into durable local memory and retrieve it by semantic similarity
  with no network call and no API key.
- Answer questions with citations, grounded only in retrieved context - never answer from
  the model's own training data when memory has nothing relevant.
- Serve three different downstream apps (second-brain, github-pr-agent,
  dreamos-command-bar) through one stable public API, so a behavior change in the kernel
  cannot silently break a caller.
- Run fully offline and keylessly in CI: 168 tests here, 334 across the kernel plus the
  three apps that import it, none needing a live model or a key.
- Be measurable, not just demoed: an eval suite that proves retrieval quality, refusal
  correctness, and freedom from hallucination and prompt injection, not only that the
  code runs.

## Constraints

- Embeddings are local-only by design (ADR 0002, `sentence-transformers`) - the
  no-API-key requirement above is not negotiable for the retrieval half of the system,
  only generation is allowed to need a key.
- SQLite plus ChromaDB, both file-based, no external database service - the kernel has
  to be importable and runnable with nothing to provision.
- The Hugging Face Space demo's free compute tier on this account is ZeroGPU (a shared,
  rationed A10G), not CPU basic - CPU basic requires a paid subscription there. That
  forced a real constraint on the demo: CUDA must never be touched outside a
  `@spaces.GPU`-decorated call, so the demo's embedder runs pinned to CPU
  (`CUDA_VISIBLE_DEVICES=""`) and only carries the decorator to satisfy the platform's
  startup check, not because the demo needs real GPU acceleration.
- No chat provider is required to exist - `ModelRouter` must degrade to "no answer
  available yet, but here is what I retrieved" rather than crash when neither Ollama nor
  a Gemini key is configured.

## Architecture

```
Callers (CLI, FastAPI gateway, Streamlit, HF Space, second-brain, github-pr-agent)
        |
personal_llm (the importable package - engine.py builds it from settings)
   |-- MemoryStore (memory/store.py): SQLite - memories, chunks, nodes, edges,
   |     entity_aliases, audit tables
   |-- VectorStore (memory/vectors.py): ChromaDB, one collection per store
   |-- ModelRouter (router/router.py): the ONLY place that calls out to a model
   |     |-- LocalEmbedder: sentence-transformers, always local, never optional
   |     |-- OllamaProvider / GeminiProvider: chat completion, tried in order,
   |     |     first healthy one wins; GeminiProvider also does vision Q&A
   |     `-- complete_with_verification(): queries every available provider and
   |           flags disagreement via embedding cosine similarity (ADR 0004) -
   |           a free, local "second opinion" check with no extra API
   |-- rag/pipeline.py (ask()): retrieve -> similarity-gate -> ground -> generate
   `-- interfaces/api.py: FastAPI gateway, token-gated on every route
```

## Data flow: asking a grounded question

1. `ask(store, vectors, router, question)` calls `semantic_search()`, which embeds the
   question locally and queries ChromaDB for the nearest chunks.
2. The top result's similarity is compared against `retrieval_min_similarity`. Below
   threshold - or nothing retrieved at all - the pipeline returns
   `"I don't have anything in memory about that."` immediately, `grounded=False`, and
   never calls a chat model. This is the honesty guarantee: the router is structurally
   unreachable on a weak retrieval, not just prompted to refuse.
3. Above threshold, the retrieved chunks are formatted into a numbered, sourced context
   block and handed to `ModelRouter.complete()` alongside the question.
4. The router tries Ollama first (if configured and healthy), then Gemini, returning the
   first successful completion; if `verify=True` it instead queries every available
   provider and flags disagreement via cosine similarity between their answers.
5. The answer is returned with per-chunk `Source` citations (doc id, source, snippet),
   and the interaction is written back into memory as its own episodic record - the
   system remembers that it was asked something, not just what it answered.

## Components

| Component | File | Responsibility |
|---|---|---|
| MemoryStore | `memory/store.py` (427 lines) | SQLite schema - memories, chunks, a knowledge-graph shape (nodes/edges/entity_aliases), and an append-only audit log |
| VectorStore | `memory/vectors.py` | ChromaDB wrapper, one collection per store instance |
| ModelRouter | `router/router.py` | provider selection, health caching, embedding, the verification/disagreement check |
| LocalEmbedder | `router/providers.py` | lazy-loaded `sentence-transformers`, the only embedding path that exists |
| rag/pipeline.py | 84 lines | the `ask()` function: retrieve, similarity-gate, ground, generate, log |
| FastAPI gateway | `interfaces/api.py` (257 lines) | the stable HTTP surface; every route requires `X-DreamOS-Token` and rejects any request carrying a browser `Origin` header |
| CLI / Streamlit / HF Space | `interfaces/` | thin clients over the same engine, no logic of their own |

## Failure modes

| Failure | Effect | Mitigation |
|---|---|---|
| No chat provider configured (no Ollama, no Gemini key) | `ask()` on a question that clears the retrieval bar has nowhere to generate from | `ModelRouter.complete()` raises a `RouterError` naming exactly what to configure, not a raw exception; retrieval itself still works with zero providers |
| Retrieval finds something, but not enough | wrong or fabricated answer | the similarity gate refuses before generation is ever called - a structural guarantee, not a prompt instruction |
| A browser page tries to call the gateway cross-origin | CSRF-style abuse of the local API | any request carrying an `Origin` header is rejected outright, since no real local caller ever sends one |
| Two chat providers disagree | a plausible-sounding answer that one model would not stand behind | `complete_with_verification()` embeds and cosine-compares every available provider's answer, flagging disagreement below a 0.6 threshold instead of silently returning the first one |
| HF Space demo's host is ZeroGPU, not CPU basic | the platform refuses to start the Space at all without a `@spaces.GPU` function, and CUDA touched outside one raises immediately | `CUDA_VISIBLE_DEVICES=""` keeps the embedder on CPU always; a no-op `@spaces.GPU` wrapper on the one function that needs it satisfies the platform's startup check |

## Tradeoffs

- **SQLite + ChromaDB over a managed vector database**: the whole point is
  zero-provisioning importability - the cost is no multi-writer concurrency and no
  network access to the memory from another machine, which no current caller needs.
- **Local-only embeddings over a hosted embedding API**: guarantees the no-key retrieval
  requirement and keeps CI keyless, at the cost of embedding quality being whatever a
  small local model gives you, and a real (if small) model-load latency on first use.
- **Router tries providers in order rather than always calling every provider**: cheap
  and fast by default; the more expensive multi-provider path exists only when a caller
  explicitly opts into `verify=True`.
- **Hard similarity gate over "instruct the model to refuse"**: an LLM asked to refuse
  when context is weak will sometimes refuse anyway that it can answer; gating in code
  before the model is ever called removes that failure mode entirely, at the cost of one
  more tunable threshold to get right.

## Scaling (what would change first)

1. ChromaDB out of single-process, file-based mode into a served instance, once more than
   one process needs to write to the same memory store concurrently - not needed by any
   current caller, all of which own their own store.
2. A real embedding-model server (batched, GPU-backed) if ingest volume ever grows past
   what a lazily-loaded local model comfortably handles per process.
3. The knowledge-graph tables (`nodes`/`edges`/`entity_aliases`) already exist in the
   schema for this; NEXUS (an experiment built on this kernel) intentionally stopped
   before scaling entity extraction past a small gate - see `zaid-os` memory
   `project-nexus` for why.

## Security

- Every route on the FastAPI gateway requires `X-DreamOS-Token`, a secret generated once
  and persisted outside the agent's own workspace directory so a compromised agent loop
  can never read its own auth token.
- Any request carrying a browser `Origin` header is rejected outright - CSRF hardening
  against a page trying to reach the local gateway cross-origin.
- On the public HF Space demo, a visitor's Gemini key is used only for that one request,
  passed straight into a fresh per-instance `GeminiProvider(api_key=...)`, and never
  touches the shared process environment or gets logged - so two visitors' keys can never
  cross.
- `.env` is never read directly by an agent working on this repo; values are always asked
  of the human.

## Observability

Currently: no structured per-call log of provider, latency, or cost - `ModelRouter`
returns which provider actually answered (`Completion.provider`) and the RAG pipeline
logs `grounded`/`disagreement` to the audit table, but nothing aggregates this into a
dashboard or a regression trend over time. The eval suite (`evals/SCORECARD.md`) is the
closest thing to observability today: correctness 6/6, recall@1 100% (n=6), refusal 9/9,
0 hallucination violations, prompt-injection isolation PASS, all offline and
deterministic, wired into CI as a build-failing regression gate.

## Cost

$0 for retrieval always (local embeddings, no key needed). Generation is $0 when Ollama
is running locally; otherwise it needs a Gemini key, free-tier-eligible
(`aistudio.google.com/apikey`). The HF Space demo costs nothing to host (ZeroGPU is a
free, rationed tier) and nothing to operate, since each visitor supplies their own key
for the Ask tab - the kernel itself never holds a shared, billable credential.

## Future

- Structured per-call cost/latency logging, matching what CivilizationOS's `LLMRouter`
  already does, so the eval suite's numbers and a live dashboard tell the same story.
- Decide whether the knowledge-graph tables graduate from "exists in the schema" to an
  actively-used entity-extraction path, or stay dormant - currently paused by design
  (NEXUS Phase 1 stopped on purpose, not blocked).
