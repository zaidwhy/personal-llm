"""Base tool interface. Every tool is a typed function with a declared permission tier -
nothing the agent calls is untyped or unaudited (docs/TDD.md Security & Privacy section)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from .schemas import ToolPermission


class ToolError(Exception):
    """Raised by a tool's run() on expected failure; caught and reported to the agent."""


class Tool(ABC):
    name: str
    description: str
    permission: ToolPermission
    args_schema: type[BaseModel]

    @abstractmethod
    def run(self, args: BaseModel) -> str:
        """Execute the tool and return a plain-text observation for the agent."""
