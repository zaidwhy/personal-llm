"""Permission-gated tool dispatch. The agent never calls a tool directly - it always
goes through here, so every invocation is checked and every result is uniform."""

from __future__ import annotations

from pydantic import ValidationError

from .base import Tool, ToolError
from .schemas import ToolPermission, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def specs(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "permission": tool.permission,
                "args_schema": tool.args_schema.model_json_schema(),
            }
            for tool in self._tools.values()
        ]

    def prompt_listing(self) -> str:
        lines = []
        for tool in self._tools.values():
            fields = tool.args_schema.model_fields
            arg_desc = ", ".join(f"{name}: {field.annotation.__name__}" for name, field in fields.items())
            lines.append(f"- {tool.name}({arg_desc}) [{tool.permission}]: {tool.description}")
        return "\n".join(lines)

    def invoke(self, name: str, raw_args: dict, allowed_permissions: set[ToolPermission]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(ok=False, error=f"unknown tool '{name}'")
        if tool.permission not in allowed_permissions:
            return ToolResult(
                ok=False,
                error=f"tool '{name}' requires '{tool.permission}' permission, which is not allowed for this run",
            )
        try:
            parsed_args = tool.args_schema(**raw_args)
        except ValidationError as exc:
            return ToolResult(ok=False, error=f"invalid arguments for '{name}': {exc}")
        try:
            output = tool.run(parsed_args)
        except ToolError as exc:
            return ToolResult(ok=False, error=str(exc))
        except Exception as exc:  # tools must not crash the agent loop
            return ToolResult(ok=False, error=f"tool '{name}' failed unexpectedly: {exc}")
        return ToolResult(ok=True, output=output)
