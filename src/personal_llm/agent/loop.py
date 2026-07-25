"""Plan-act-reflect loop (docs/TDD.md Agent Framework). One base Agent; specialized
agents are just different registries/permissions/prompts, not new code (docs/PRD.md)."""

from __future__ import annotations

import json

from personal_llm.memory.store import MemoryStore
from personal_llm.prompts import load_prompt
from personal_llm.router import Message, ModelRouter
from personal_llm.tools.registry import ToolRegistry
from personal_llm.tools.schemas import ToolPermission

from .schemas import AgentResult, AgentStep, StepRecord


def _parse_tool_args(raw: str) -> tuple[dict, str | None]:
    try:
        parsed = json.loads(raw) if raw and raw.strip() else {}
    except json.JSONDecodeError as exc:
        return {}, str(exc)
    if not isinstance(parsed, dict):
        return {}, "tool args must be a JSON object"
    return parsed, None

DEFAULT_MAX_STEPS = 6
DEFAULT_ALLOWED_PERMISSIONS: frozenset[ToolPermission] = frozenset({"read_only"})


class Agent:
    def __init__(
        self,
        router: ModelRouter,
        registry: ToolRegistry,
        store: MemoryStore,
        allowed_permissions: set[ToolPermission] | frozenset[ToolPermission] = DEFAULT_ALLOWED_PERMISSIONS,
        max_steps: int = DEFAULT_MAX_STEPS,
    ) -> None:
        self._router = router
        self._registry = registry
        self._store = store
        self._allowed_permissions = set(allowed_permissions)
        self._max_steps = max_steps

    def _build_messages(self, goal: str, transcript: list[tuple[AgentStep, str]]) -> list[Message]:
        system = Message(role="system", content=load_prompt("agent_system").format(tools=self._registry.prompt_listing()))
        lines = [f"Goal: {goal}"]
        for step, observation in transcript:
            lines.append(f"\nThought: {step.thought}")
            if step.tool is not None:
                lines.append(f"Action: {step.tool.name}({step.tool.args})")
                lines.append(f"Observation: <observation>{observation}</observation>")
        lines.append("\nWhat is your next step?" if transcript else "\nWhat is your first step?")
        return [system, Message(role="user", content="\n".join(lines))]

    def run(self, goal: str) -> AgentResult:
        transcript: list[tuple[AgentStep, str]] = []
        records: list[StepRecord] = []

        for _ in range(self._max_steps):
            messages = self._build_messages(goal, transcript)
            completion = self._router.complete(messages, schema=AgentStep)
            step = completion.parsed if isinstance(completion.parsed, AgentStep) else None
            if step is None:
                step = AgentStep(thought="(unparsed model output)", final_answer=completion.text)

            if step.tool is None:
                final = step.final_answer or "Done."
                records.append(StepRecord(thought=step.thought))
                self._store.log("agent", "final_answer", {"goal": goal, "answer": final})
                return AgentResult(goal=goal, final_answer=final, steps=records, succeeded=True)

            parsed_args, args_error = _parse_tool_args(step.tool.args)
            if args_error is not None:
                observation = f"ERROR: invalid tool args - {args_error}"
                tool_ok = False
            else:
                result = self._registry.invoke(step.tool.name, parsed_args, self._allowed_permissions)
                observation = result.output if result.ok else f"ERROR: {result.error}"
                tool_ok = result.ok

            self._store.log(
                "agent",
                "tool_call",
                {"goal": goal, "tool": step.tool.name, "args": parsed_args, "ok": tool_ok},
            )
            records.append(
                StepRecord(
                    thought=step.thought,
                    tool_name=step.tool.name,
                    tool_args=parsed_args,
                    observation=observation,
                )
            )
            transcript.append((step, observation))

        self._store.log("agent", "max_steps_exceeded", {"goal": goal, "steps": self._max_steps})
        return AgentResult(
            goal=goal,
            final_answer=f"I couldn't finish within {self._max_steps} steps. Try narrowing the goal.",
            steps=records,
            succeeded=False,
        )
