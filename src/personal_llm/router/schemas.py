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
