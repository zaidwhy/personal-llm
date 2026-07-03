# ADR 0001: Vector store = Chroma, Graph store = SQLite+NetworkX (not Neo4j)

**Status:** Accepted

**Context:** Need a vector store for semantic memory and a graph store for the knowledge graph, at personal scale (thousands-tens of thousands of items), running free and local.

**Decision:** Chroma (embedded, persistent, no server) for vectors. SQLite `nodes`/`edges` tables + NetworkX for in-memory traversal for the graph - no dedicated graph database yet.

**Alternatives considered:** `sqlite-vec` (simpler but less mature filtering); Neo4j/Kùzu for the graph (adds a server or a new embedded dependency for a graph that will have a few thousand edges in v0.1).

**Consequences:** Fast to build, zero ops burden, fully local. Revisit (swap behind `graph/kg.py` and `memory/vectors.py` interfaces) if the graph exceeds ~100k edges or needs Cypher-style multi-hop queries.
