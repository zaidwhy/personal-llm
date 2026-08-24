"""Typed memory records - see docs/TDD.md section 1 for the taxonomy mapping."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .identity import deterministic_entity_id, normalize_canonical_key

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
    """Identity is deterministic, not caller-chosen: `id` is always
    sha1(f"{type}|{canonical_key}"), recomputed in `_assign_deterministic_identity`
    regardless of what is passed in, so the same (type, name) always resolves to the
    same node instead of a fresh random id each mention (the bug that produced 21
    separate "Personal LLM" nodes). `canonical_key` defaults to the normalized form of
    `name` when not given explicitly."""

    id: str = ""
    type: str
    name: str
    canonical_key: str = ""
    meta: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _assign_deterministic_identity(self) -> "KGNode":
        if not self.canonical_key:
            self.canonical_key = normalize_canonical_key(self.name)
        self.id = deterministic_entity_id(self.type, self.canonical_key)
        return self


class KGEdge(BaseModel):
    src: str
    rel: str
    dst: str
    weight: float = 1.0
    meta: dict = Field(default_factory=dict)
