"""Typed shape for externally-fetched content (Gmail/Drive, etc.) - see
docs/DECISIONS/0005-external-integrations-via-mcp-bridge.md for why this package never
does its own OAuth: the fetch happens outside personal_llm, this is only the ingestion side."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ExternalSource = Literal["gmail", "drive"]


class ExternalItem(BaseModel):
    source: ExternalSource
    external_id: str
    title: str
    content: str
    url: str | None = None


class SyncResult(BaseModel):
    ingested: int = 0
    skipped_existing: int = 0
    doc_ids: list[str] = Field(default_factory=list)
