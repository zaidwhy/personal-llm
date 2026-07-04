from __future__ import annotations

from datetime import datetime, timedelta, timezone

from personal_llm.memory.types import MemoryRecord
from personal_llm.review.weekly import ReviewInsights, generate_review


def _old_iso(days: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_review_counts_recent_and_forgotten_items(store, router):
    store.add_memory(MemoryRecord(kind="episodic", content="did a thing today", importance=0.4))

    old_important = MemoryRecord(
        kind="fact", content="renew passport", importance=0.9, created_at=_old_iso(30)
    )
    store.add_memory(old_important)

    old_unimportant = MemoryRecord(
        kind="fact", content="liked a random post", importance=0.2, created_at=_old_iso(30)
    )
    store.add_memory(old_unimportant)

    router.script = [ReviewInsights(highlights=["did a thing today"], forgotten_worth_revisiting=["renew passport"])]

    report = generate_review(store, router, days=7)

    assert report.recent_count == 1
    assert report.forgotten_count == 1
    assert report.insights.forgotten_worth_revisiting == ["renew passport"]


def test_review_ignores_recently_accessed_important_items(store, router):
    important = MemoryRecord(kind="fact", content="important but touched", importance=0.9, created_at=_old_iso(30))
    store.add_memory(important)
    store.touch_memory(important.id)  # access_count becomes 1, so it's not "forgotten"

    router.script = [ReviewInsights()]
    report = generate_review(store, router, days=7)

    assert report.forgotten_count == 0


def test_review_falls_back_to_empty_insights_when_unparsed(store, router):
    report = generate_review(store, router, days=7)  # default canned_parsed=None

    assert report.insights == ReviewInsights()


def test_review_stores_itself_as_episodic_memory(store, router):
    router.script = [ReviewInsights(highlights=["found something useful"])]

    generate_review(store, router, days=7)

    episodics = store.list_memories(kind="episodic")
    assert any("found something useful" in m.content for m in episodics)


def test_review_logs_to_audit(store, router):
    router.script = [ReviewInsights()]

    generate_review(store, router, days=7)

    rows = store.recent_audit(actor="system")
    assert any(r["action"] == "weekly_review" for r in rows)
