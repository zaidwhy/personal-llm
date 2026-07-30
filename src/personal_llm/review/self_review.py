"""Weekly self-review report generator: audit log + NIGHT_SHIFT.md -> deterministic markdown.

PROJECT-GENESIS.md section 9 Tier 5 item 37 (aliased Tier 9 item 75); section 6 "AI that
designs better AIs" names the audit log and NIGHT_SHIFT.md as its first two data sources
for a self-review. This is a different thing from `review/weekly.py`'s proactive review,
which reads memory CONTENT and calls a model to surface insights about what Zaid has been
thinking about. This module reads the SYSTEM's own recent activity instead: MemoryStore's
audit trail (every ingest/ask/remember/... call already logs itself via `store.log()`)
plus the ai-ecosystem Night Shift build log, and renders a deterministic markdown summary
of both - no model call, so the same inputs always produce the same report, byte for byte
(the explicit verification bar the task queue names).

No personal_llm.router import: this never calls a model.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from personal_llm.memory.store import MemoryStore

_ENTRY_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2}).*$", re.MULTILINE)


@dataclass(frozen=True)
class NightShiftEntry:
    date: str
    heading: str
    body: str


def parse_night_shift_log(text: str) -> list[NightShiftEntry]:
    """Split NIGHT_SHIFT.md's append-only log into per-heading entries.

    Each entry starts at a `## YYYY-MM-DD...` heading (the log's own convention, e.g.
    "## 2026-07-23 (Night Shift)") and runs to the next such heading or end of file. Text
    before the first heading (the file's own top-level title/intro line) is ignored.
    """
    matches = list(_ENTRY_HEADING_RE.finditer(text))
    entries: list[NightShiftEntry] = []
    for i, match in enumerate(matches):
        heading = match.group(0)[3:].strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        entries.append(NightShiftEntry(date=match.group(1), heading=heading, body=body))
    return entries


def _entry_date(entry: NightShiftEntry) -> datetime:
    return datetime.strptime(entry.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def recent_night_shift_entries(
    entries: Sequence[NightShiftEntry], *, days: int = 7, as_of: datetime | None = None
) -> list[NightShiftEntry]:
    """Entries dated within the last `days` days of `as_of` (default: now), oldest first."""
    as_of = as_of or datetime.now(timezone.utc)
    cutoff = as_of - timedelta(days=days)
    recent = [e for e in entries if _entry_date(e) >= cutoff]
    recent.sort(key=lambda e: e.date)
    return recent


@dataclass(frozen=True)
class AuditSummary:
    total: int
    by_actor: dict[str, int]
    by_action: dict[str, int]


def summarize_audit(entries: Sequence[dict]) -> AuditSummary:
    """Deterministic counts over a list of audit records (MemoryStore.recent_audit shape:
    each a dict with at least `actor` and `action` keys). Sorted alphabetically by key so
    two calls with the same entries in a different order produce identical output.
    """
    by_actor = Counter(e["actor"] for e in entries)
    by_action = Counter(e["action"] for e in entries)
    return AuditSummary(
        total=len(entries),
        by_actor=dict(sorted(by_actor.items())),
        by_action=dict(sorted(by_action.items())),
    )


def _within_days(iso_ts: str, days: int, as_of: datetime) -> bool:
    try:
        ts = datetime.fromisoformat(iso_ts)
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts >= as_of - timedelta(days=days)


def render_self_review_markdown(
    *,
    generated_at: str,
    days: int,
    audit_summary: AuditSummary,
    night_shift_entries: Sequence[NightShiftEntry],
) -> str:
    """Deterministic markdown - no randomness, no data besides what is passed in."""
    lines: list[str] = []
    lines.append(f"# Weekly Self-Review ({days}d)")
    lines.append("")
    lines.append(f"Generated: {generated_at}")
    lines.append("")
    lines.append("## Audit activity")
    lines.append("")
    lines.append(f"**Total events:** {audit_summary.total}")
    lines.append("")
    lines.append("By actor:")
    if audit_summary.by_actor:
        for actor, count in audit_summary.by_actor.items():
            lines.append(f"- {actor}: {count}")
    else:
        lines.append("- (no audit events in this window)")
    lines.append("")
    lines.append("By action:")
    if audit_summary.by_action:
        for action, count in audit_summary.by_action.items():
            lines.append(f"- {action}: {count}")
    else:
        lines.append("- (no audit events in this window)")
    lines.append("")
    lines.append("## Night Shift entries")
    lines.append("")
    if night_shift_entries:
        for entry in night_shift_entries:
            lines.append(f"- {entry.heading}")
    else:
        lines.append("- (no NIGHT_SHIFT.md entries in this window, or the log was not available)")
    lines.append("")
    return "\n".join(lines)


def generate_self_review(
    store: MemoryStore,
    *,
    night_shift_log_path: str | Path | None = None,
    days: int = 7,
    audit_limit: int = 500,
    as_of: datetime | None = None,
) -> str:
    """Convenience wrapper: reads a real MemoryStore's audit log (and, if present, the
    Night Shift build log at `night_shift_log_path`) and renders the markdown report.

    A missing `night_shift_log_path` (unset, or the file does not exist) degrades to an
    audit-only report rather than raising - the log lives in the sibling ai-ecosystem
    repo and is not guaranteed to be checked out next to this one.
    """
    as_of = as_of or datetime.now(timezone.utc)
    audit = [
        entry
        for entry in store.recent_audit(limit=audit_limit)
        if _within_days(entry["ts"], days, as_of)
    ]
    summary = summarize_audit(audit)

    night_shift_entries: list[NightShiftEntry] = []
    if night_shift_log_path is not None:
        path = Path(night_shift_log_path)
        if path.exists():
            all_entries = parse_night_shift_log(path.read_text(encoding="utf-8"))
            night_shift_entries = recent_night_shift_entries(all_entries, days=days, as_of=as_of)

    return render_self_review_markdown(
        generated_at=as_of.isoformat(),
        days=days,
        audit_summary=summary,
        night_shift_entries=night_shift_entries,
    )
