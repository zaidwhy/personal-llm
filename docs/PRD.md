# Personal LLM - Product Requirements Document

**Status:** v0.1 in active development
**Owner:** Zaid Ali Syed
**Tagline:** Your Second Brain. Your Digital Twin. Your Personal AI.

---

## 1. Executive Summary

Personal LLM is a local-first, privacy-preserving personal AI engine designed to know its user deeply, remember continuously, and eventually act autonomously on their behalf. Unlike ChatGPT, Claude, Gemini, or voice assistants (Siri/Alexa/Google Assistant), it is not a stateless chat product - it is infrastructure: a memory system, retrieval engine, model router, agent framework, and knowledge graph that this user's other projects (Recall, CivilizationOS, portfolio, future work) build on top of instead of re-implementing.

This document defines the full product vision (every subsystem from the original brief) and then triages it into what actually gets built now versus later, so ambition doesn't collapse into an unshippable everything-at-once project.

## 2. Vision

An AI that:
- **Knows** the user - their projects, goals, preferences, writing/coding style.
- **Remembers** - conversations, decisions, documents, and events accumulate into durable memory instead of vanishing at the end of a chat session.
- **Understands** context and intent, not just literal commands.
- **Learns** continuously from feedback and usage, without requiring model fine-tuning.
- **Protects** the user's data - local-first, encryptable, auditable, under the user's control.
- **Works for** the user - eventually completing multi-step tasks autonomously, with permission boundaries.

## 3. User Personas

| Persona | Description | Primary needs |
|---|---|---|
| **Zaid (primary)** | AI learner and builder, building public credibility via GitHub/LinkedIn, juggling multiple concurrent projects | Remembers project context across sessions; surfaces forgotten tasks; answers questions grounded in his own notes/code, not generic web knowledge |
| **Busy professional** | Manages email, calendar, docs across many tools | Proactive summaries, deadline tracking, less context-switching |
| **Researcher/learner** | Ingesting papers, courses, articles | RAG over a growing personal knowledge base with citations, skill-gap tracking |

## 4. Functional Requirements

Priority key: **P0** = v0.1 (this build) · **P1** = v0.2-v1.0 · **P2** = post-v1 · **P3** = speculative/research-gated, explicitly out of scope for now.

### 4.1 Memory
| Requirement | Priority |
|---|---|
| Ingest text/markdown/PDF into durable storage | P0 |
| Chunk + embed + semantic search (vector recall) | P0 |
| Episodic memory (timestamped events/interactions) | P0 |
| Importance scoring or memory items | P0 |
| Memory decay (old, rarely-accessed memories lose weight) | P0 |
| Memory consolidation / deduplication | P0 |
| Conflict resolution (contradicting facts) | P1 |
| Manual memory editing/deletion (user-facing) | P1 |
| Procedural memory ("how I like X done", reusable recipes) | P1 |
| Full-life ingestion (emails, calendar, files, messages, habits) | P2 |

### 4.2 Reasoning
| Requirement | Priority |
|---|---|
| Grounded Q&A with citations from retrieved memory | P0 |
| Explicit uncertainty ("not in memory") vs hallucination avoidance | P0 |
| Self-critique / reflection pass on generated answers | P1 |
| Multi-step planning for agent tasks | P1 |
| Distinct "reasoning modes" (logical/scientific/creative/strategic) as separate models | **P3 - reject as stated.** These are prompt strategies + verification passes on one strong model, not separate trained models. Building six bespoke reasoning engines is a research program, not a feature. |

### 4.3 Model Orchestration
| Requirement | Priority |
|---|---|
| Single router interface for chat completion + embeddings | P0 |
| Cloud provider (Gemini free tier) | P0 |
| Optional local provider (Ollama) with automatic fallback | P0 |
| Confidence/verification signal on outputs | P1 |
| Multi-provider (paid models, OpenAI, etc. via router) | P1 |
| Automatic model selection by task complexity | P2 |

### 4.4 Knowledge Graph
| Requirement | Priority |
|---|---|
| Entity/relation extraction from ingested content | P0 (lite) |
| Node/edge storage, 1-hop traversal to enrich retrieval | P0 (lite) |
| Rich graph across people/projects/files/calendar/emails | P1-P2 |
| Dedicated graph DB (Kùzu/Neo4j) at scale | P2 |

### 4.5 Agents & Tools
| Requirement | Priority |
|---|---|
| Base agent abstraction (role + tools + memory scope + permissions) | P1 |
| Typed tool-calling layer with audit log | P1 |
| Specialized agents (research, coding, writing, email, etc.) | P1-P2, added as config on the base agent, not new code |
| Fully autonomous multi-agent workforce managing the user's life | **P3** - real but distant; requires the permission/safety layer to mature first |

### 4.6 Proactivity
| Requirement | Priority |
|---|---|
| Scheduled memory consolidation / weekly review job | P1 |
| Surfacing forgotten tasks, deadlines | P1-P2 |
| Full proactive life-management (spending anomalies, burnout detection, etc.) | P2-P3, needs real integrations first |

### 4.7 Voice & Vision
| Requirement | Priority |
|---|---|
| Text-only interaction (CLI, API, Streamlit chat) | P0 |
| Speech-to-text / text-to-speech | P2 |
| Real-time interruption, speaker recognition, voice cloning | **P3** - genuinely hard, high infra cost, low priority relative to memory/RAG value |
| Vision (screenshots, documents, whiteboards) | P2 |
| Live camera/desktop understanding | P3 |

### 4.8 Integrations
| Requirement | Priority |
|---|---|
| Local filesystem ingestion | P0 |
| Gmail/Drive (via existing MCP connectors already available in this environment) | P1 |
| GitHub, Notion, Calendar, Slack, etc. | P2 |
| IoT/mobile | P3 |

### 4.9 Developer Platform
| Requirement | Priority |
|---|---|
| Engine importable as a Python package by other local projects | P0 |
| Stable FastAPI surface for non-Python callers | P1 |
| Public SDK / plugin marketplace for third parties | **P3** - premature before there's a single trusted user (Zaid) fully served |

## 5. Non-Functional Requirements

| Category | Requirement |
|---|---|
| **Privacy** | All memory stored locally by default (SQLite + Chroma on-disk). No data leaves the device except explicit calls to a chosen cloud model provider. |
| **Cost** | Must run end-to-end at **$0** using free-tier Gemini + local embeddings. Paid providers opt-in only. |
| **Offline capability** | Ingest, retrieve, and search must work with zero network access (local embeddings). Generation degrades gracefully (clear error) if no provider is reachable. |
| **Latency** | Retrieval < 500ms for a personal-scale corpus (thousands of chunks). Generation latency bounded by provider. |
| **Reliability** | Transient provider errors (429/5xx) auto-retried with backoff (pattern proven in `resume-job-fit-ai/analyzer.py`). |
| **Portability** | All state in two portable artifacts: a SQLite file and a Chroma directory. Backup = copy `data/`. |
| **Auditability** | Every memory write and (from v0.2) every tool action logged to an `audit` table. |
| **Testability** | All LLM calls mockable; CI runs without secrets. |

## 6. Success Metrics

| Phase | Metric |
|---|---|
| v0.1 | Ingest a folder of real notes; ask a question; get a cited, grounded answer; correctly say "not in memory" for an absent fact; works with network disabled except for the generation call. |
| v0.2 | An agent completes a 2+ step task using at least one tool, fully audited. |
| v1.0 | Used daily by Zaid for at least one real task (e.g. querying his own project notes) for 2+ consecutive weeks. |

## 7. Out of Scope (explicitly, for now)

Voice cloning, real-time multi-speaker voice, autonomous multi-agent "life management," public plugin marketplace, mobile/IoT integration, continuous model fine-tuning. These remain in the vision (see `ROADMAP.md` v2/v3) but are not designed in detail until v1 is real and used.
