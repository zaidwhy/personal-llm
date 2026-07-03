"""Typed memory records - see docs/TDD.md section 1 for the taxonomy mapping."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

MemoryKind = Literal["episodic", "semantic", "procedural", "fact"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid.uuid4().hex


class MemoryRecord(BaseModel):
    id: str = Field(default_factory=new_id)
    created_at: str = Field(default_factory=_now)
    kind: MemoryKind = "episodic"
    content: str
    source: str = ""
    importance: float = 0.5
    last_accessed: str | None = None
    access_count: int = 0
    archived: bool = False
    vector_id: str | None = None
    meta: dict = Field(default_factory=dict)


class Chunk(BaseModel):
    id: str = Field(default_factory=new_id)
    doc_id: str
    ord: int
    text: str
    vector_id: str | None = None
    created_at: str = Field(default_factory=_now)


class KGNode(BaseModel):
    id: str = Field(default_factory=new_id)
    type: str
    name: str
    meta: dict = Field(default_factory=dict)


class KGEdge(BaseModel):
    src: str
    rel: str
    dst: str
    weight: float = 1.0
    meta: dict = Field(default_factory=dict)
