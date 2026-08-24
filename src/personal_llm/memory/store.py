"""SQLite-backed store for memories, chunks, the knowledge graph, and the audit log.

Schema mirrors docs/ARCHITECTURE.md exactly - keep them in sync if either changes.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .identity import normalize_canonical_key, subsumes
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
  canonical_key TEXT NOT NULL DEFAULT '',
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

CREATE TABLE IF NOT EXISTS entity_aliases (
  alias_norm TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  source TEXT,
  confidence REAL NOT NULL DEFAULT 1.0,
  PRIMARY KEY (alias_norm, entity_id)
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
CREATE INDEX IF NOT EXISTS idx_entity_aliases_entity ON entity_aliases(entity_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MemoryStore:
    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            self._migrate_nodes_table(conn)

    def _migrate_nodes_table(self, conn: sqlite3.Connection) -> None:
        """Backfill `canonical_key` and its unique index for a nodes table created
        before this column existed. A brand-new table already has the column (it is in
        _SCHEMA) and 0 rows, so this is a no-op there. For a pre-existing table, any
        rows sharing a (type, canonical_key) after backfill are collapsed onto the
        first one (by rowid) and edges are repointed - the same consolidation
        scripts/rebuild_entities.py performs, done defensively here so opening any old
        DB through this class never crashes on the new unique index."""
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(nodes)").fetchall()}
        if "canonical_key" not in columns:
            conn.execute("ALTER TABLE nodes ADD COLUMN canonical_key TEXT NOT NULL DEFAULT ''")

        rows = conn.execute("SELECT rowid, id, type, name, canonical_key FROM nodes").fetchall()
        for row in rows:
            if not row["canonical_key"]:
                conn.execute(
                    "UPDATE nodes SET canonical_key = ? WHERE rowid = ?",
                    (normalize_canonical_key(row["name"]), row["rowid"]),
                )

        groups: dict[tuple[str, str], list[str]] = {}
        for row in conn.execute("SELECT id, type, canonical_key FROM nodes").fetchall():
            groups.setdefault((row["type"], row["canonical_key"]), []).append(row["id"])
        for (_type, _key), ids in groups.items():
            if len(ids) <= 1:
                continue
            keep, *drop = ids
            for dupe_id in drop:
                _fold_node_into(conn, keep, dupe_id)
        _dedupe_edges(conn)
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_nodes_type_canonical_key ON nodes(type, canonical_key)")

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

    def doc_exists(self, doc_id: str) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM chunks WHERE doc_id = ? LIMIT 1", (doc_id,)).fetchone()
        return row is not None

    def get_chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" * len(chunk_ids))
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM chunks WHERE id IN ({placeholders})", chunk_ids).fetchall()
        by_id = {row["id"]: _row_to_chunk(row) for row in rows}
        return [by_id[cid] for cid in chunk_ids if cid in by_id]

    def all_chunks(self) -> list[Chunk]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM chunks ORDER BY doc_id, ord").fetchall()
        return [_row_to_chunk(r) for r in rows]

    # --- knowledge graph --------------------------------------------------------

    def upsert_entity(self, node: KGNode) -> str:
        """Insert a new entity, or fold a repeat mention into the existing row for its
        (type, canonical_key). This is the fix for the old add_node behavior, which
        was `INSERT OR REPLACE` keyed on a random uuid id - so it never deduped and
        every mention became a new row."""
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO nodes (id, type, name, canonical_key, meta)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(type, canonical_key) DO UPDATE SET
                     name = excluded.name,
                     meta = excluded.meta""",
                (node.id, node.type, node.name, node.canonical_key, json.dumps(node.meta)),
            )
            conn.execute(
                "INSERT OR IGNORE INTO entity_aliases (alias_norm, entity_id, source, confidence) "
                "VALUES (?, ?, ?, ?)",
                (node.canonical_key, node.id, "kg_extraction", 1.0),
            )
        return node.id

    def add_node(self, node: KGNode) -> str:
        """Thin compatibility shim - delegates to upsert_entity. Kept because other
        callers may still say add_node; upsert_entity is the real implementation."""
        return self.upsert_entity(node)

    def add_entity_alias(self, alias_norm: str, entity_id: str, source: str, confidence: float = 1.0) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO entity_aliases (alias_norm, entity_id, source, confidence) "
                "VALUES (?, ?, ?, ?)",
                (alias_norm, entity_id, source, confidence),
            )

    def add_edge(self, edge: KGEdge) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO edges (src, rel, dst, weight, meta) VALUES (?, ?, ?, ?, ?)",
                (edge.src, edge.rel, edge.dst, edge.weight, json.dumps(edge.meta)),
            )

    def all_nodes(self) -> list[KGNode]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM nodes").fetchall()
        return [
            KGNode(
                id=r["id"], type=r["type"], name=r["name"],
                canonical_key=r["canonical_key"], meta=json.loads(r["meta"] or "{}"),
            )
            for r in rows
        ]

    def all_edges(self) -> list[KGEdge]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM edges").fetchall()
        return [
            KGEdge(src=r["src"], rel=r["rel"], dst=r["dst"], weight=r["weight"], meta=json.loads(r["meta"] or "{}"))
            for r in rows
        ]

    def clear_graph(self) -> None:
        """Wipe nodes/edges/entity_aliases. They are derived data (re-extractable from
        chunks), used by scripts/rebuild_entities.py to force a clean rebuild rather
        than trying to reconcile old random-id nodes in place."""
        with self._connect() as conn:
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM entity_aliases")

    def merge_subsumed_people(self) -> int:
        """Fold a person's short name into their full name ("Zaid" into "Zaid Ali Syed"),
        repointing edges and keeping the short form in `entity_aliases` so a later
        mention still resolves. Returns how many nodes were folded away.

        Restricted to people on purpose. Name subsumption is a reliable coreference
        signal for humans and an unreliable one for everything else, where a longer name
        usually means a different thing - see identity.subsumes."""
        folded = 0
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, canonical_key FROM nodes WHERE type = 'person'"
            ).fetchall()
            # Longest first, so a short form always folds into the fullest name available
            # rather than into an intermediate one.
            people = sorted(rows, key=lambda r: len(r["canonical_key"].split()), reverse=True)
            absorbed: set[str] = set()
            for keeper in people:
                if keeper["id"] in absorbed:
                    continue
                for candidate in people:
                    if candidate["id"] in absorbed or candidate["id"] == keeper["id"]:
                        continue
                    if not subsumes(keeper["canonical_key"], candidate["canonical_key"]):
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO entity_aliases (alias_norm, entity_id, source, confidence) "
                        "VALUES (?, ?, ?, ?)",
                        (candidate["canonical_key"], keeper["id"], "name_subsumption", 0.9),
                    )
                    _fold_node_into(conn, keeper["id"], candidate["id"])
                    absorbed.add(candidate["id"])
                    folded += 1
            _dedupe_edges(conn)
        return folded

    # --- audit --------------------------------------------------------------

    def log(self, actor: str, action: str, detail: dict | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit (ts, actor, action, detail) VALUES (?, ?, ?, ?)",
                (_now(), actor, action, json.dumps(detail or {})),
            )

    def recent_audit(self, actor: str | None = None, limit: int = 50) -> list[dict]:
        query = "SELECT ts, actor, action, detail FROM audit"
        params: list = []
        if actor is not None:
            query += " WHERE actor = ?"
            params.append(actor)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            {"ts": r["ts"], "actor": r["actor"], "action": r["action"], "detail": json.loads(r["detail"] or "{}")}
            for r in rows
        ]

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


def _fold_node_into(conn: sqlite3.Connection, keep_id: str, drop_id: str) -> None:
    """Repoint every edge off `drop_id` onto `keep_id`, redirect its aliases, and delete
    it. Callers run _dedupe_edges afterwards, because repointing can produce an edge that
    now points at itself.

    UPDATE OR IGNORE, not plain UPDATE: when the keeper already carries the same
    (src, rel, dst), repointing raises on the UNIQUE constraint mid-fold and aborts the
    whole merge. Skipping those rows is right - the edge being repointed is a duplicate of
    one the keeper already has - and the DELETE below clears whatever the skip left behind
    still attached to drop_id."""
    conn.execute("UPDATE OR IGNORE edges SET src = ? WHERE src = ?", (keep_id, drop_id))
    conn.execute("UPDATE OR IGNORE edges SET dst = ? WHERE dst = ?", (keep_id, drop_id))
    conn.execute("DELETE FROM edges WHERE src = ? OR dst = ?", (drop_id, drop_id))
    conn.execute("UPDATE OR IGNORE entity_aliases SET entity_id = ? WHERE entity_id = ?", (keep_id, drop_id))
    conn.execute("DELETE FROM entity_aliases WHERE entity_id = ?", (drop_id,))
    conn.execute("DELETE FROM nodes WHERE id = ?", (drop_id,))


def _dedupe_edges(conn: sqlite3.Connection) -> None:
    # Folding two nodes together can leave an edge pointing at itself, which carries no
    # information and would inflate the edge count, so drop those as well.
    conn.execute("DELETE FROM edges WHERE src = dst")
    conn.execute("DELETE FROM edges WHERE rowid NOT IN (SELECT MIN(rowid) FROM edges GROUP BY src, rel, dst)")
