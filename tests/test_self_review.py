"""Weekly self-review report generator: audit-log parsing, NIGHT_SHIFT.md parsing,
deterministic markdown rendering, and the real-store wrapper."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from personal_llm.review.self_review import (
    AuditSummary,
    NightShiftEntry,
    generate_self_review,
    parse_night_shift_log,
    recent_night_shift_entries,
    render_self_review_markdown,
    summarize_audit,
)

_AS_OF = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)

_SAMPLE_LOG = """# Night Shift Log

Append-only. One entry per night, newest last.

## 2026-07-21 (Night Shift)

- **Task:** did something on the 21st.
- **Result:** it worked.

## 2026-07-23 (Night Shift)

- **Task:** did something on the 23rd.
- **Result:** it also worked.

## 2026-07-27 (Night Shift)

- **Task:** did something on the 27th.
- **Result:** worked too.
"""


def test_parse_night_shift_log_splits_on_date_headings():
    entries = parse_night_shift_log(_SAMPLE_LOG)
    assert [e.date for e in entries] == ["2026-07-21", "2026-07-23", "2026-07-27"]
    assert entries[0].heading == "2026-07-21 (Night Shift)"
    assert "did something on the 21st" in entries[0].body


def test_parse_night_shift_log_ignores_text_before_first_heading():
    entries = parse_night_shift_log(_SAMPLE_LOG)
    assert not any("Append-only" in e.body for e in entries)


def test_parse_night_shift_log_empty_text_returns_empty():
    assert parse_night_shift_log("") == []


def test_parse_night_shift_log_last_entry_runs_to_end_of_file():
    entries = parse_night_shift_log(_SAMPLE_LOG)
    assert "worked too" in entries[-1].body


def test_recent_night_shift_entries_filters_by_window():
    entries = parse_night_shift_log(_SAMPLE_LOG)
    recent = recent_night_shift_entries(entries, days=7, as_of=_AS_OF)
    assert [e.date for e in recent] == ["2026-07-23", "2026-07-27"]


def test_recent_night_shift_entries_wider_window_includes_more():
    entries = parse_night_shift_log(_SAMPLE_LOG)
    recent = recent_night_shift_entries(entries, days=30, as_of=_AS_OF)
    assert [e.date for e in recent] == ["2026-07-21", "2026-07-23", "2026-07-27"]


def test_recent_night_shift_entries_sorted_oldest_first():
    entries = [
        NightShiftEntry(date="2026-07-27", heading="h27", body=""),
        NightShiftEntry(date="2026-07-23", heading="h23", body=""),
    ]
    recent = recent_night_shift_entries(entries, days=30, as_of=_AS_OF)
    assert [e.date for e in recent] == ["2026-07-23", "2026-07-27"]


def test_recent_night_shift_entries_empty_input_returns_empty():
    assert recent_night_shift_entries([], as_of=_AS_OF) == []


def test_summarize_audit_counts_by_actor_and_action():
    entries = [
        {"actor": "system", "action": "ingest", "ts": "..."},
        {"actor": "system", "action": "ingest", "ts": "..."},
        {"actor": "user", "action": "ask", "ts": "..."},
    ]
    summary = summarize_audit(entries)
    assert summary.total == 3
    assert summary.by_actor == {"system": 2, "user": 1}
    assert summary.by_action == {"ask": 1, "ingest": 2}


def test_summarize_audit_empty_input():
    summary = summarize_audit([])
    assert summary == AuditSummary(total=0, by_actor={}, by_action={})


def test_summarize_audit_order_independent():
    forward = summarize_audit(
        [{"actor": "a", "action": "x"}, {"actor": "b", "action": "y"}]
    )
    backward = summarize_audit(
        [{"actor": "b", "action": "y"}, {"actor": "a", "action": "x"}]
    )
    assert forward == backward


def test_render_self_review_markdown_includes_all_sections():
    summary = AuditSummary(total=3, by_actor={"system": 2, "user": 1}, by_action={"ask": 1, "ingest": 2})
    entries = [NightShiftEntry(date="2026-07-27", heading="2026-07-27 (Night Shift)", body="...")]
    markdown = render_self_review_markdown(
        generated_at=_AS_OF.isoformat(), days=7, audit_summary=summary, night_shift_entries=entries
    )
    assert "Weekly Self-Review (7d)" in markdown
    assert "**Total events:** 3" in markdown
    assert "- system: 2" in markdown
    assert "- ingest: 2" in markdown
    assert "2026-07-27 (Night Shift)" in markdown


def test_render_self_review_markdown_empty_sections_show_placeholders():
    summary = AuditSummary(total=0, by_actor={}, by_action={})
    markdown = render_self_review_markdown(
        generated_at=_AS_OF.isoformat(), days=7, audit_summary=summary, night_shift_entries=[]
    )
    assert "(no audit events in this window)" in markdown
    assert "(no NIGHT_SHIFT.md entries in this window, or the log was not available)" in markdown


def test_render_self_review_markdown_is_deterministic():
    summary = AuditSummary(total=1, by_actor={"system": 1}, by_action={"ingest": 1})
    entries = [NightShiftEntry(date="2026-07-27", heading="h", body="")]
    first = render_self_review_markdown(
        generated_at="2026-07-28T00:00:00+00:00", days=7, audit_summary=summary, night_shift_entries=entries
    )
    second = render_self_review_markdown(
        generated_at="2026-07-28T00:00:00+00:00", days=7, audit_summary=summary, night_shift_entries=entries
    )
    assert first == second


def test_generate_self_review_reads_real_store_audit_log(store):
    # store.log() timestamps at real "now", so this deliberately leaves `as_of` at its
    # default (also real "now") rather than a fixed fictional date - see the module
    # docstring's determinism claim, which is about render_self_review_markdown given
    # fixed inputs, not about wall-clock-coupled integration tests like this one.
    store.log("system", "ingest", {"doc_id": "a"})
    store.log("system", "ask", {"question": "?"})

    report = generate_self_review(store, days=7)
    assert "**Total events:** 2" in report
    assert "- system: 2" in report
    assert "- ask: 1" in report
    assert "- ingest: 1" in report


def test_generate_self_review_excludes_events_outside_window(store):
    store.log("system", "ingest", {})  # logged at real "now"
    far_future = datetime.now(timezone.utc) + timedelta(days=30)

    report = generate_self_review(store, days=7, as_of=far_future)
    assert "**Total events:** 0" in report


def test_generate_self_review_without_night_shift_log_path(store):
    report = generate_self_review(store, night_shift_log_path=None, days=7)
    assert "no NIGHT_SHIFT.md entries in this window, or the log was not available" in report


def test_generate_self_review_missing_night_shift_file_degrades_gracefully(store, tmp_path):
    missing = tmp_path / "does-not-exist" / "NIGHT_SHIFT.md"
    report = generate_self_review(store, night_shift_log_path=missing, days=7)
    assert "no NIGHT_SHIFT.md entries in this window, or the log was not available" in report


def test_generate_self_review_reads_real_night_shift_file(store, tmp_path):
    log_path = tmp_path / "NIGHT_SHIFT.md"
    log_path.write_text(_SAMPLE_LOG, encoding="utf-8")

    report = generate_self_review(store, night_shift_log_path=log_path, days=7, as_of=_AS_OF)
    assert "2026-07-23 (Night Shift)" in report
    assert "2026-07-27 (Night Shift)" in report
    assert "2026-07-21 (Night Shift)" not in report  # outside the 7-day window
