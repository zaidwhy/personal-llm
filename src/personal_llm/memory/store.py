"""SQLite-backed store for memories, chunks, the knowledge graph, and the audit log.

Schema mirrors docs/ARCHITECTURE.md exactly - keep them in sync if either changes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .types import Chunk, KGEdge, KGNode, MemoryKind, MemoryRecord

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  content TEXT NOT NULL,
  source TEXT,
  importance REAL NOT NULL DEFAULT 0.5,
  last_accessed TEXT,
  access_count INTEGER NOT NULL DEFAULT 0,
  archived INTEGER NOT NULL DEFAULT 0,
  vector_id TEXT,
  meta TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  ord INTEGER NOT NULL,
  text TEXT NOT NULL,
  vector_id TEXT,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  meta TEXT
);

CREATE TABLE IF NOT EXISTS edges (
  src TEXT NOT NULL,
  rel TEXT NOT NULL,
  dst TEXT NOT NULL,
  weight REAL NOT NULL DEFAULT 1.0,
  meta TEXT,
  PRIMARY KEY (src, rel, dst)
);

CREATE TABLE IF NOT EXISTS audit (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  detail TEXT
);

CREATE INDEX IF NOT EXISTS idx_memories_kind ON memories(kind);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- memories -----------------------------------------------------------

    def add_memory(self, record: MemoryRecord) -> str:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO memories
                   (id, created_at, kind, content, source, importance, last_accessed,
                    access_count, archived, vector_id, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    record.id, record.created_at, record.kind, record.content, record.source,
                    record.importance, record.last_accessed, record.access_count,
                    int(record.archived), record.vector_id, json.dumps(record.meta),
                ),
            )
        return record.id

    def get_memory(self, memory_id: str) -> MemoryRecord | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return _row_to_memory(row) if row else None

    def get_memories(self, memory_ids: list[str]) -> list[MemoryRecord]:
        if not memory_ids:
            return []
        placeholders = ",".join("?" * len(memory_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE id IN ({placeholders})", memory_ids
            ).fetchall()
        by_id = {row["id"]: _row_to_memory(row) for row in rows}
        return [by_id[mid] for mid in memory_ids if mid in by_id]

    def get_memories_by_vector_ids(self, vector_ids: list[str]) -> dict[str, MemoryRecord]:
        if not vector_ids:
            return {}
        placeholders = ",".join("?" * len(vector_ids))
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM memories WHERE vector_id IN ({placeholders})", vector_ids
            ).fetchall()
        return {row["vector_id"]: _row_to_memory(row) for row in rows}

    def list_memories(self, kind: MemoryKind | None = None, include_archived: bool = False) -> list[MemoryRecord]:
        query = "SELECT * FROM memories WHERE 1=1"
        params: list = []
        if kind is not None:
            query += " AND kind = ?"
            params.append(kind)
        if not include_archived:
            query += " AND archived = 0"
        query += " ORDER BY created_at DESC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [_row_to_memory(r) for r in rows]

    def touch_memory(self, memory_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE memories SET access_count = access_count + 1, last_accessed = ? WHERE id = ?",
                (_now(), memory_id),
            )

    def set_importance(self, memory_id: str, importance: float) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE memories SET importance = ? WHERE id = ?", (importance, memory_id))

    def archive_memory(self, memory_id: str) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE memories SET archived = 1 WHERE id = ?", (memory_id,))

    def update_meta(self, memory_id: str, meta: dict) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE memories SET meta = ? WHERE id = ?", (json.dumps(meta), memory_id))

    # --- chunks ---------------------------------------------------------------

    def add_chunk(self, chunk: Chunk) -> str:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO chunks (id, doc_id, ord, text, vector_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (chunk.id, chunk.doc_id, chunk.ord, chunk.text, chunk.vector_id, chunk.created_at),
            )
        return chunk.id

    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids).fetchall()
        by_id = {row["id"]: _row_to_chunk(row) for row in rows}
        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    # --- knowledge graph --------------------------------------------------------

    def add_node(self, node: KGNode) -> str:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO nodes (id, type, name, meta) VALUES (?, ?, ?, ?)",
                (node.id, node.type, node.name, json.dumps(node.meta)),
            )
        return node.id

    def add_edge(self, edge: KGEdge) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO edges (src, rel, dst, weight, meta) VALUES (?, ?, ?, ?, ?)",
                (edge.src, edge.rel, edge.dst, edge.weight, json.dumps(edge.meta)),
            )

    def all_nodes(self) -> list[KGNode]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM nodes").fetchall()
        return [KGNode(id=r["id"], type=r["type"], name=r["name"], meta=json.loads(r["meta"] or "{}")) for r in rows]

    def all_edges(self) -> list[KGEdge]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM edges").fetchall()
        return [
            KGEdge(src=r["src"], rel=r["rel"], dst=r["dst"], weight=r["weight"], meta=json.loads(r["meta"] or "{}"))
            for r in rows
        ]

    # --- audit --------------------------------------------------------------

    def log(self, actor: str, action: str, detail: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit (ts, actor, action, detail) VALUES (?, ?, ?, ?)",
                (_now(), actor, action, json.dumps(detail or {})),
            )

    # --- stats ----------------------------------------------------------------

    def stats(self) -> dict:
        with self._connect() as conn:
            memory_count = conn.execute("SELECT COUNT(*) FROM memories WHERE archived = 0").fetchone()[0]
            archived_count = conn.execute("SELECT COUNT(*) FROM memories WHERE archived = 1").fetchone()[0]
            chunk_count = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            node_count = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            edge_count = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
            by_kind_rows = conn.execute(
                "SELECT kind, COUNT(*) as c FROM memories WHERE archived = 0 GROUP BY kind"
            ).fetchall()
        return {
            "memories": memory_count,
            "archived_memories": archived_count,
            "chunks": chunk_count,
            "kg_nodes": node_count,
            "kg_edges": edge_count,
            "memories_by_kind": {r["kind"]: r["c"] for r in by_kind_rows},
        }


def _row_to_memory(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        created_at=row["created_at"],
        kind=row["kind"],
        content=row["content"],
        source=row["source"] or "",
        importance=row["importance"],
        last_accessed=row["last_accessed"],
        access_count=row["access_count"],
        archived=bool(row["archived"]),
        vector_id=row["vector_id"],
        meta=json.loads(row["meta"] or "{}"),
    )


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        id=row["id"], doc_id=row["doc_id"], ord=row["ord"], text=row["text"],
        vector_id=row["vector_id"], created_at=row["created_at"],
    )
