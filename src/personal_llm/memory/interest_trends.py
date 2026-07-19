"""Interest-trend detector: keyword-frequency drift over ingestion timestamps.

PROJECT-GENESIS.md sec. 9 Tier 4 item 33 (aliased Tier 9 item 77): "personal-llm:
interest-trend detector over ingestion timestamps". Every MemoryRecord already
carries `created_at`; this buckets records into two adjacent, equal-length time
windows - "recent" and the "previous" one right before it - and compares keyword
frequency between them. A keyword said much more often in the recent window than
the previous one is a rising interest; one said much less is a fading one. Pure
frequency counting, not a topic model: no clustering, no embeddings, no model call
- same "detect candidates, never interpret" contract as second-brain's near_dup.py
and contradictions.py.

No personal_llm.router import: this never calls a model, so it stays fully
offline and fast to test.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Protocol, Sequence

from personal_llm.memory.store import MemoryStore
from personal_llm.memory.time_utils import days_since

_WORD_RE = re.compile(r"[a-z]{3,}")

_STOPWORDS = frozenset(
    {
        "the", "and", "for", "are", "was", "were", "with", "that", "this",
        "have", "has", "had", "not", "but", "you", "your", "from", "they",
        "will", "would", "could", "should", "about", "into", "over", "then",
        "than", "just", "like", "also", "been", "being", "did", "does",
        "doing", "when", "what", "which", "who", "why", "how", "there",
        "here", "our", "their", "its", "his", "her", "she", "him", "them",
        "today", "yesterday", "one", "two", "get", "got", "still",
    }
)


class _TimedNote(Protocol):
    content: str
    created_at: str


@dataclass(frozen=True)
class TrendingKeyword:
    keyword: str
    recent_count: int
    previous_count: int
    delta: int


def extract_keywords(content: str) -> Counter:
    """Lowercased, stopword-filtered, 3+ letter word counts for one note's text."""
    words = _WORD_RE.findall(content.lower())
    return Counter(w for w in words if w not in _STOPWORDS)


def _window_counts(notes: Sequence[_TimedNote], min_days: float, max_days: float) -> Counter:
    counts: Counter = Counter()
    for note in notes:
        age = days_since(note.created_at)
        if min_days <= age < max_days:
            counts.update(extract_keywords(note.content))
    return counts


def detect_interest_trends(
    notes: Sequence[_TimedNote],
    *,
    window_days: float = 7.0,
    k: int = 10,
    min_count: int = 2,
) -> list[TrendingKeyword]:
    """Rank keywords by how much more (or less) they appear in the recent window
    than the equal-length window immediately before it.

    "Recent" is notes aged [0, window_days) days; "previous" is [window_days,
    2 x window_days) days - two adjacent slices of ingestion history, so the
    comparison is always like-for-like (same span length, no seasonal skew from
    comparing a week to a whole month). `delta = recent_count - previous_count`;
    positive deltas are rising interests, negative ones are fading. A keyword is
    only considered if it appears at least `min_count` times in EITHER window, to
    keep single-mention noise out of the ranking. Ranked by absolute delta
    descending (biggest swings first, rising or fading); ties break alphabetically
    for a deterministic order.
    """
    recent = _window_counts(notes, 0.0, window_days)
    previous = _window_counts(notes, window_days, 2 * window_days)

    keywords = {kw for kw, count in recent.items() if count >= min_count} | {
        kw for kw, count in previous.items() if count >= min_count
    }

    trends = [
        TrendingKeyword(kw, recent.get(kw, 0), previous.get(kw, 0), recent.get(kw, 0) - previous.get(kw, 0))
        for kw in keywords
    ]
    trends.sort(key=lambda t: (-abs(t.delta), t.keyword))
    return trends[:k]


def detect_interest_trends_in_store(
    store: MemoryStore,
    *,
    window_days: float = 7.0,
    k: int = 10,
    min_count: int = 2,
) -> list[TrendingKeyword]:
    """Convenience wrapper: same as `detect_interest_trends`, reading directly from
    a MemoryStore's non-archived memories."""
    return detect_interest_trends(
        store.list_memories(), window_days=window_days, k=k, min_count=min_count
    )
