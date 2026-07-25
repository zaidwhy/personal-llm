"""Proactive review (docs/ROADMAP.md v0.3): surfaces useful things without being asked,
instead of waiting for a question. Looks at recent activity plus important memories that
have never been revisited, and asks the model for concrete, specific takeaways."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from personal_llm.memory.store import MemoryStore
from personal_llm.memory.time_utils import days_since
from personal_llm.memory.types import MemoryRecord
from personal_llm.prompts import load_prompt
from personal_llm.router import Message, ModelRouter

_FORGOTTEN_IMPORTANCE_FLOOR = 0.6
_FORGOTTEN_AFTER_DAYS = 7.0
_MAX_ITEMS_IN_PROMPT = 20


class ReviewInsights(BaseModel):
    highlights: list[str] = Field(default_factory=list)
    forgotten_worth_revisiting: list[str] = Field(default_factory=list)
    suggested_actions: list[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    generated_at: str
    days: int
    recent_count: int
    forgotten_count: int
    insights: ReviewInsights


def _recent_memories(store: MemoryStore, days: int) -> list[MemoryRecord]:
    return [m for m in store.list_memories() if days_since(m.created_at) <= days]


def _forgotten_candidates(store: MemoryStore) -> list[MemoryRecord]:
    return [
        m
        for m in store.list_memories()
        if m.importance >= _FORGOTTEN_IMPORTANCE_FLOOR
        and m.access_count == 0
        and days_since(m.created_at) >= _FORGOTTEN_AFTER_DAYS
    ]


def _build_context(recent: list[MemoryRecord], forgotten: list[MemoryRecord]) -> str:
    lines = ["Recent activity:"]
    lines += [f"- ({m.kind}) {m.content}" for m in recent[:_MAX_ITEMS_IN_PROMPT]] or ["- (nothing recent)"]
    lines.append("\nImportant items not revisited in a while:")
    lines += [
        f"- ({m.kind}, importance {m.importance:.2f}) {m.content}" for m in forgotten[:_MAX_ITEMS_IN_PROMPT]
    ] or ["- (none)"]
    return "\n".join(lines)


def generate_review(store: MemoryStore, router: ModelRouter, days: int = 7) -> ReviewReport:
    recent = _recent_memories(store, days)
    forgotten = _forgotten_candidates(store)
    context = _build_context(recent, forgotten)

    messages = [
        Message(role="system", content=load_prompt("review_system")),
        Message(role="user", content=f"<context>\n{context}\n</context>"),
    ]
    completion = router.complete(messages, schema=ReviewInsights)
    insights = completion.parsed if isinstance(completion.parsed, ReviewInsights) else ReviewInsights()

    report = ReviewReport(
        generated_at=datetime.now(timezone.utc).isoformat(),
        days=days,
        recent_count=len(recent),
        forgotten_count=len(forgotten),
        insights=insights,
    )

    store.add_memory(
        MemoryRecord(
            kind="episodic",
            content=f"Weekly review ({days}d): {'; '.join(insights.highlights) or 'no highlights'}",
            source="review",
            importance=0.5,
        )
    )
    store.log("system", "weekly_review", report.model_dump())
    return report
