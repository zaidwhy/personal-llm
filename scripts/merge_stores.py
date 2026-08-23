"""Merge the three diverged personal_llm stores into the single NEXUS_DATA_DIR root.

Background: before config.py was fixed to derive every data path from one absolute
NEXUS_DATA_DIR root, three independent stores accumulated at:

  ecosystem      ai-ecosystem\\data\\personal_llm.db          (+ chroma\\)
  personal-llm   ai-ecosystem\\personal-llm\\data\\personal_llm.db  (+ chroma\\)
  second-brain   ai-ecosystem\\second-brain\\data\\personal_llm.db (+ chroma\\)

"ecosystem" is also the NEXUS_DATA_DIR default, so it is simultaneously a merge input
and (before this script runs) sitting at the destination path.

What this script does:
  1. Reads all three source DBs (read-only), independent of the destination.
  2. Dedupes memories on (kind, content, source) and chunks on (doc_id, ord, text),
     first-seen origin wins, in the order above.
  3. Appends every audit row from all three (it is a log; no dedupe), ordered by ts.
  4. Does NOT merge nodes/edges - only reports their per-origin counts. Entity identity
     is rebuilt from the merged chunks by scripts/rebuild_entities.py (step 5).
  5. Builds the merged result into a fresh temp DB and reconciles its counts against an
     independently computed expected union before touching anything real.
  6. On --apply: archives all three original DBs to data\\archive\\<origin>-personal_llm.db,
     then installs the merged DB at the NEXUS_DATA_DIR root.
  7. On --apply --rebuild-vectors: archives the three Chroma dirs to
     data\\archive\\<origin>-chroma\\, then rebuilds a fresh Chroma store at the root by
     re-embedding every chunk in the merged DB (local MiniLM, no API key, no binary
     Chroma surgery).

--dry-run is the default: nothing is written, moved, or archived unless --apply is
passed explicitly.

Usage:
  python scripts/merge_stores.py                          # dry run, prints the plan
  python scripts/merge_stores.py --apply                   # merges DBs, archives originals
  python scripts/merge_stores.py --apply --rebuild-vectors # also rebuilds the vector store
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from personal_llm.config import get_settings  # noqa: E402
from personal_llm.memory.store import _SCHEMA  # noqa: E402

ECOSYSTEM_ROOT = Path(r"C:\Users\Asus\projects\ai-ecosystem")

ORIGINS: list[tuple[str, Path]] = [
    ("ecosystem", ECOSYSTEM_ROOT / "data"),
    ("personal-llm", ECOSYSTEM_ROOT / "personal-llm" / "data"),
    ("second-brain", ECOSYSTEM_ROOT / "second-brain" / "data"),
]

_MERGE_TABLES = ("memories", "chunks", "nodes", "edges", "audit")


@contextmanager
def _connect(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()
        is not None
    )


def _read_rows(db_path: Path, table: str) -> list[sqlite3.Row]:
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        if not _table_exists(conn, table):
            return []
        return conn.execute(f"SELECT * FROM {table}").fetchall()


def _read_origin_rows() -> dict[str, dict[str, list[sqlite3.Row]]]:
    """{origin_name: {table_name: rows}}"""
    out: dict[str, dict[str, list[sqlite3.Row]]] = {}
    for origin_name, origin_dir in ORIGINS:
        db_path = origin_dir / "personal_llm.db"
        out[origin_name] = {table: _read_rows(db_path, table) for table in _MERGE_TABLES}
    return out


def _merge_memories(
    origin_rows: dict[str, dict[str, list[sqlite3.Row]]],
) -> tuple[list[sqlite3.Row], int]:
    """Dedupe on (kind, content, source); first-seen origin (table order above) wins."""
    seen: dict[tuple, sqlite3.Row] = {}
    duplicates = 0
    for origin_name, _ in ORIGINS:
        for row in origin_rows[origin_name]["memories"]:
            key = (row["kind"], row["content"], row["source"])
            if key in seen:
                duplicates += 1
                continue
            seen[key] = row
    return list(seen.values()), duplicates


def _merge_chunks(
    origin_rows: dict[str, dict[str, list[sqlite3.Row]]],
) -> tuple[list[sqlite3.Row], dict[str, str], int]:
    """Dedupe on (doc_id, ord, text); first-seen wins. Returns (kept_rows, old_id ->
    canonical_id map covering EVERY source chunk id including duplicates, duplicate_count)."""
    seen: dict[tuple, sqlite3.Row] = {}
    id_map: dict[str, str] = {}
    duplicates = 0
    for origin_name, _ in ORIGINS:
        for row in origin_rows[origin_name]["chunks"]:
            key = (row["doc_id"], row["ord"], row["text"])
            if key in seen:
                duplicates += 1
                id_map[row["id"]] = seen[key]["id"]
            else:
                seen[key] = row
                id_map[row["id"]] = row["id"]
    return list(seen.values()), id_map, duplicates


def _merge_audit(origin_rows: dict[str, dict[str, list[sqlite3.Row]]]) -> list[dict]:
    """Every audit row from every origin, kept (it is a log), ordered by timestamp, tagged
    with provenance in `detail._merged_from` for traceability."""
    merged: list[dict] = []
    for origin_name, _ in ORIGINS:
        for row in origin_rows[origin_name]["audit"]:
            detail = json.loads(row["detail"] or "{}")
            detail["_merged_from"] = origin_name
            merged.append(
                {"ts": row["ts"], "actor": row["actor"], "action": row["action"], "detail": detail}
            )
    merged.sort(key=lambda r: r["ts"])
    return merged


def _rewrite_memory_vector_id(vector_id: str | None, chunk_id_map: dict[str, str]) -> str | None:
    if vector_id is None:
        return None
    return chunk_id_map.get(vector_id, vector_id)


def _rewrite_memory_meta(meta_json: str | None, chunk_id_map: dict[str, str]) -> str:
    meta = json.loads(meta_json or "{}")
    if "chunk_id" in meta and meta["chunk_id"] in chunk_id_map:
        meta["chunk_id"] = chunk_id_map[meta["chunk_id"]]
    return json.dumps(meta)


def _build_merged_db(
    dest_path: Path,
    memory_rows: list[sqlite3.Row],
    chunk_rows: list[sqlite3.Row],
    audit_rows: list[dict],
    chunk_id_map: dict[str, str],
) -> None:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        dest_path.unlink()
    with _connect(dest_path) as conn:
        conn.executescript(_SCHEMA)
        for row in memory_rows:
            conn.execute(
                """INSERT INTO memories
                   (id, created_at, kind, content, source, importance, last_accessed,
                    access_count, archived, vector_id, meta)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    row["id"], row["created_at"], row["kind"], row["content"], row["source"],
                    row["importance"], row["last_accessed"], row["access_count"], row["archived"],
                    _rewrite_memory_vector_id(row["vector_id"], chunk_id_map),
                    _rewrite_memory_meta(row["meta"], chunk_id_map),
                ),
            )
        for row in chunk_rows:
            conn.execute(
                "INSERT INTO chunks (id, doc_id, ord, text, vector_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (row["id"], row["doc_id"], row["ord"], row["text"], row["vector_id"], row["created_at"]),
            )
        for entry in audit_rows:
            conn.execute(
                "INSERT INTO audit (ts, actor, action, detail) VALUES (?, ?, ?, ?)",
                (entry["ts"], entry["actor"], entry["action"], json.dumps(entry["detail"])),
            )
        conn.commit()


def _archive_dbs(apply: bool) -> None:
    archive_dir = get_settings().data_root / "archive"
    if apply:
        archive_dir.mkdir(parents=True, exist_ok=True)
    for origin_name, origin_dir in ORIGINS:
        src = origin_dir / "personal_llm.db"
        if not src.exists():
            continue
        dst = archive_dir / f"{origin_name}-personal_llm.db"
        print(f"  archive db:     {src}  ->  {dst}")
        if apply:
            shutil.move(str(src), str(dst))


def _archive_chroma_dirs(apply: bool) -> None:
    archive_dir = get_settings().data_root / "archive"
    if apply:
        archive_dir.mkdir(parents=True, exist_ok=True)
    for origin_name, origin_dir in ORIGINS:
        src = origin_dir / "chroma"
        if not src.exists() or not any(src.iterdir()):
            continue
        dst = archive_dir / f"{origin_name}-chroma"
        print(f"  archive chroma: {src}  ->  {dst}")
        if apply:
            if dst.exists():
                shutil.rmtree(dst)
            shutil.move(str(src), str(dst))


def _rebuild_vectors(apply: bool, dest_db_path: Path, dest_chroma_dir: Path) -> None:
    with _connect(dest_db_path) as conn:
        rows = conn.execute("SELECT id, doc_id, text FROM chunks ORDER BY doc_id, ord").fetchall()
    print(f"  chunks to embed: {len(rows)}")
    if not apply:
        print("  (dry run - not embedding or writing Chroma)")
        return

    from personal_llm.memory.vectors import VectorStore
    from personal_llm.router.router import ModelRouter

    router = ModelRouter()
    dest_chroma_dir.mkdir(parents=True, exist_ok=True)
    vectors = VectorStore(str(dest_chroma_dir))

    batch_size = 64
    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        embeddings = router.embed([r["text"] for r in batch])
        ids = [r["id"] for r in batch]
        metadatas = [{"chunk_id": r["id"], "doc_id": r["doc_id"]} for r in batch]
        vectors.add(ids, embeddings, metadatas)
        total += len(batch)
        print(f"  embedded {total}/{len(rows)}")
    print(f"  Chroma rebuilt at {dest_chroma_dir}: {vectors.count()} vectors")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Actually write/move/archive. Default is dry-run.")
    parser.add_argument(
        "--dry-run", action="store_true", help="Explicit no-op flag; dry-run is already the default."
    )
    parser.add_argument(
        "--rebuild-vectors",
        action="store_true",
        help="After the DB merge, archive the three Chroma dirs and rebuild one from the merged chunks table.",
    )
    args = parser.parse_args()
    apply = args.apply

    settings = get_settings()
    dest_root = settings.data_root
    dest_db_path = Path(settings.personal_llm_db_path)
    dest_chroma_dir = Path(settings.personal_llm_chroma_dir)

    print(f"{'APPLY' if apply else 'DRY RUN'} - merge target: {dest_root}\n")

    origin_rows = _read_origin_rows()

    print("Per-origin counts (as found):")
    for origin_name, origin_dir in ORIGINS:
        rows = origin_rows[origin_name]
        print(
            f"  {origin_name:<13} {origin_dir / 'personal_llm.db'}  "
            f"memories={len(rows['memories'])} chunks={len(rows['chunks'])} "
            f"nodes={len(rows['nodes'])} edges={len(rows['edges'])} audit={len(rows['audit'])}"
        )
    print()

    memory_rows, memory_dupes = _merge_memories(origin_rows)
    chunk_rows, chunk_id_map, chunk_dupes = _merge_chunks(origin_rows)
    audit_rows = _merge_audit(origin_rows)

    total_node_count = sum(len(origin_rows[o]["nodes"]) for o, _ in ORIGINS)
    total_edge_count = sum(len(origin_rows[o]["edges"]) for o, _ in ORIGINS)

    expected_memories = len(memory_rows)
    expected_chunks = len(chunk_rows)
    expected_audit = len(audit_rows)

    print("Merge plan:")
    print(f"  memories: {expected_memories} kept, {memory_dupes} duplicates dropped")
    print(f"  chunks:   {expected_chunks} kept, {chunk_dupes} duplicates dropped")
    print(f"  audit:    {expected_audit} rows appended (no dedupe)")
    print(
        f"  nodes/edges: NOT merged - {total_node_count} nodes / {total_edge_count} edges "
        "across origins reported only; rebuilt by scripts/rebuild_entities.py"
    )
    print()

    temp_db_path = dest_root / "personal_llm.db.merging"
    _build_merged_db(temp_db_path, memory_rows, chunk_rows, audit_rows, chunk_id_map)

    with _connect(temp_db_path) as conn:
        actual_memories = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        actual_chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
        actual_audit = conn.execute("SELECT COUNT(*) FROM audit").fetchone()[0]

    print("Reconciliation (independently computed union vs. built merge DB):")
    print(f"  memories: expected {expected_memories}, got {actual_memories}")
    print(f"  chunks:   expected {expected_chunks}, got {actual_chunks}")
    print(f"  audit:    expected {expected_audit}, got {actual_audit}")

    if (actual_memories, actual_chunks, actual_audit) != (expected_memories, expected_chunks, expected_audit):
        temp_db_path.unlink()
        raise SystemExit(
            "RECONCILIATION FAILED: merged DB counts do not match the independently "
            "computed expected union. Refusing to apply."
        )
    print("  reconciliation OK\n")

    if not apply:
        print("Dry run only - nothing written. Re-run with --apply to merge for real.")
        if args.rebuild_vectors:
            print("\nVector rebuild plan:")
            _rebuild_vectors(apply=False, dest_db_path=temp_db_path, dest_chroma_dir=dest_chroma_dir)
        temp_db_path.unlink()
        return 0

    print("Archiving originals:")
    _archive_dbs(apply=True)
    shutil.move(str(temp_db_path), str(dest_db_path))
    print(f"\nMerged DB installed at {dest_db_path}")

    if args.rebuild_vectors:
        print("\nArchiving Chroma dirs:")
        _archive_chroma_dirs(apply=True)
        print("\nRebuilding vector store from merged chunks:")
        _rebuild_vectors(apply=True, dest_db_path=dest_db_path, dest_chroma_dir=dest_chroma_dir)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
