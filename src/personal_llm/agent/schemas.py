"""Typed I/O for the agent loop - the LLM's turn is always parsed as one of these,
never free text (docs/TDD.md Agent Framework section)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ToolInvocation(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


class AgentStep(BaseModel):
    thought: str
    tool: ToolInvocation | None = None
    final_answer: str | None = None


class StepRecord(BaseModel):
    thought: str
    tool_name: str | None = None
    tool_args: dict = Field(default_factory=dict)
    observation: str | None = None


class AgentResult(BaseModel):
    goal: str
    final_answer: str
    steps: list[StepRecord] = Field(default_factory=list)
    succeeded: bool = True
