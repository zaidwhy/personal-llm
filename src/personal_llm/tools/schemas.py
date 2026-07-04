"""Typed I/O for the tool layer (docs/TDD.md section on Tool Integration)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

ToolPermission = Literal["read_only", "read_write", "network"]


class ToolResult(BaseModel):
    ok: bool
    output: str = ""
    error: str | None = None
