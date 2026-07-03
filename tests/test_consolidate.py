from datetime import datetime, timedelta, timezone

from personal_llm.memory.consolidate import consolidate, decay_and_archive, flag_duplicates
from personal_llm.memory.types import MemoryRecord


def _old_timestamp(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_decay_lowers_importance_for_stale_memories(store):
    old = MemoryRecord(kind="fact", content="old fact", importance=0.5, created_at=_old_timestamp(30))
    store.add_memory(old)

    decayed, archived = decay_and_archive(store)

    assert decayed == 1
    assert archived == 0
    assert store.get_memory(old.id).importance < 0.5


def test_decay_leaves_recent_memories_untouched(store):
    recent = MemoryRecord(kind="fact", content="recent fact", importance=0.5)
    store.add_memory(recent)

    decayed, archived = decay_and_archive(store)

    assert decayed == 0
    assert store.get_memory(recent.id).importance == 0.5


def test_archive_after_long_decay_and_low_importance(store):
    very_old = MemoryRecord(kind="fact", content="ancient", importance=0.01, created_at=_old_timestamp(200))
    store.add_memory(very_old)

    decayed, archived = decay_and_archive(store)

    assert archived == 1
    assert store.get_memory(very_old.id).archived is True


def test_flag_duplicates_marks_exact_content_matches(store):
    a = MemoryRecord(kind="semantic", content="Same content here.")
    b = MemoryRecord(kind="semantic", content="Same content here.")
    store.add_memory(a)
    store.add_memory(b)

    flagged = flag_duplicates(store)

    assert flagged == 1
    assert store.get_memory(b.id).meta.get("duplicate_of") == a.id


def test_consolidate_report_aggregates_decay_and_dedup(store):
    store.add_memory(MemoryRecord(kind="fact", content="dup"))
    store.add_memory(MemoryRecord(kind="fact", content="dup"))

    report = consolidate(store)

    assert report.duplicates_flagged == 1
