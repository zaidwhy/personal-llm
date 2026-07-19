from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from personal_llm.memory.interest_trends import (
    TrendingKeyword,
    detect_interest_trends,
    detect_interest_trends_in_store,
    extract_keywords,
)
from personal_llm.memory.types import MemoryRecord


def _iso(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


@dataclass(frozen=True)
class FakeNote:
    content: str
    created_at: str


def test_extract_keywords_lowercases_and_filters_stopwords():
    counts = extract_keywords("The Gateway auth token rotates and the token is new.")
    assert counts["token"] == 2
    assert counts["gateway"] == 1
    assert counts["auth"] == 1
    assert "the" not in counts
    assert "and" not in counts
    assert "is" not in counts  # shorter than 3 letters is already excluded by regex


def test_extract_keywords_drops_words_shorter_than_three_letters():
    assert extract_keywords("go to it") == {}


def test_rising_keyword_ranks_by_positive_delta():
    notes = [
        FakeNote("gateway auth token rotation", _iso(1)),
        FakeNote("gateway auth token again", _iso(2)),
        FakeNote("gateway token mentioned once", _iso(10)),
    ]
    trends = detect_interest_trends(notes, window_days=7, min_count=1)
    by_kw = {t.keyword: t for t in trends}
    assert by_kw["gateway"].recent_count == 2
    assert by_kw["gateway"].previous_count == 1
    assert by_kw["gateway"].delta == 1


def test_fading_keyword_has_negative_delta():
    notes = [
        FakeNote("legacy renderer bug", _iso(9)),
        FakeNote("legacy renderer flicker", _iso(10)),
        FakeNote("something unrelated", _iso(1)),
    ]
    trends = detect_interest_trends(notes, window_days=7, min_count=1)
    by_kw = {t.keyword: t for t in trends}
    assert by_kw["legacy"].recent_count == 0
    assert by_kw["legacy"].previous_count == 2
    assert by_kw["legacy"].delta == -2


def test_min_count_filters_single_mentions():
    notes = [FakeNote("obscure keyword appears once", _iso(1))]
    trends = detect_interest_trends(notes, window_days=7, min_count=2)
    assert trends == []


def test_notes_older_than_two_windows_are_excluded():
    notes = [FakeNote("ancient topic mentioned", _iso(30))]
    trends = detect_interest_trends(notes, window_days=7, min_count=1)
    assert trends == []


def test_window_boundary_is_recent_exclusive_previous_inclusive():
    # Exactly at window_days=7.0 days old must land in "previous", not "recent".
    notes = [FakeNote("boundary keyword case", _iso(7.0))]
    trends = detect_interest_trends(notes, window_days=7, min_count=1)
    by_kw = {t.keyword: t for t in trends}
    assert by_kw["boundary"].recent_count == 0
    assert by_kw["boundary"].previous_count == 1


def test_k_limits_result_count():
    notes = [FakeNote(f"uniqueword{i} appears twice", _iso(1)) for i in range(5)] * 2
    trends = detect_interest_trends(notes, window_days=7, min_count=1, k=2)
    assert len(trends) == 2


def test_ties_broken_alphabetically():
    notes = [FakeNote("zeta alpha", _iso(1)), FakeNote("zeta alpha", _iso(2))]
    trends = detect_interest_trends(notes, window_days=7, min_count=1)
    assert [t.keyword for t in trends] == ["alpha", "zeta"]


def test_empty_input_returns_empty():
    assert detect_interest_trends([]) == []


def test_detect_interest_trends_in_store_reads_real_memory_store(store):
    store.add_memory(MemoryRecord(content="gateway auth token", created_at=_iso(1)))
    store.add_memory(MemoryRecord(content="gateway auth token", created_at=_iso(2)))
    store.add_memory(MemoryRecord(content="unrelated old note", created_at=_iso(20)))

    trends = detect_interest_trends_in_store(store, window_days=7, min_count=1)
    keywords = {t.keyword for t in trends}
    assert "gateway" in keywords
    assert "unrelated" not in keywords  # older than the 2x window, excluded
