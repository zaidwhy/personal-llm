"""Typed I/O for the model router - kept provider-agnostic on purpose."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Completion(BaseModel):
    text: str
    parsed: object | None = Field(default=None, description="Structured output if a schema was requested.")
    provider: str
    model: str


class VerifiedCompletion(BaseModel):
    primary: Completion
    alternates: list[Completion] = Field(default_factory=list)
    agreement_scores: list[float] = Field(
        default_factory=list, description="Cosine similarity of each alternate's text to the primary's."
    )
    disagreement: bool = False
