"""Shared time helpers - kept in one place so recency/decay/review logic can't drift apart."""

from __future__ import annotations

from datetime import datetime, timezone


def days_since(iso_ts: str) -> float:
    try:
        ts = datetime.fromisoformat(iso_ts)
    except ValueError:
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - ts).total_seconds() / 86400.0)
