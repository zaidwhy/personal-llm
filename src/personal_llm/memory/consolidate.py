"""Batch memory consolidation: decay, dedup, conflict flagging (docs/TDD.md section 1).

Run periodically (e.g. via CLI `consolidate` command). Never hard-deletes -
memories are archived (soft-deleted) only once both stale and unimportant.
"""

from __future__ import annotations

import hashlib

from pydantic import BaseModel

from .store import MemoryStore
from .time_utils import days_since

_DECAY_MULTIPLIER = 0.9  # importance *= this, per stale memory, each consolidation pass
_DECAY_AFTER_DAYS = 14.0
_ARCHIVE_IMPORTANCE_FLOOR = 0.05
_ARCHIVE_AFTER_DAYS = 90.0


class ConsolidationReport(BaseModel):
    decayed: int = 0
    archived: int = 0
    duplicates_flagged: int = 0


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().lower().encode("utf-8")).hexdigest()


def decay_and_archive(store: MemoryStore) -> tuple[int, int]:
    decayed = 0
    archived = 0
    for memory in store.list_memories():
        basis = memory.last_accessed or memory.created_at
        age_days = days_since(basis)
        if age_days <= _DECAY_AFTER_DAYS:
            continue
        new_importance = max(0.0, memory.importance * _DECAY_MULTIPLIER)
        store.set_importance(memory.id, new_importance)
        decayed += 1
        if new_importance < _ARCHIVE_IMPORTANCE_FLOOR and age_days > _ARCHIVE_AFTER_DAYS:
            store.archive_memory(memory.id)
            archived += 1
    return decayed, archived


def flag_duplicates(store: MemoryStore) -> int:
    """Exact-content duplicates within the same kind get meta.duplicate_of set on the newer copy.

    Fuzzy/semantic duplicate detection and contradiction detection are P1 (docs/TDD.md) -
    left as a documented gap, not built here, to avoid an LLM-per-pair cost explosion.
    """
    seen: dict[tuple[str, str], str] = {}
    flagged = 0
    for memory in sorted(store.list_memories(), key=lambda m: m.created_at):
        key = (memory.kind, _content_hash(memory.content))
        if key in seen:
            memory.meta["duplicate_of"] = seen[key]
            store.update_meta(memory.id, memory.meta)
            flagged += 1
        else:
            seen[key] = memory.id
    return flagged


def consolidate(store: MemoryStore) -> ConsolidationReport:
    decayed, archived = decay_and_archive(store)
    duplicates = flag_duplicates(store)
    store.log("system", "consolidate", {"decayed": decayed, "archived": archived, "duplicates": duplicates})
    return ConsolidationReport(decayed=decayed, archived=archived, duplicates_flagged=duplicates)
