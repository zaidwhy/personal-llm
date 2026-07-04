from __future__ import annotations

from personal_llm.agent import Agent, AgentStep, ToolInvocation
from personal_llm.memory.ingest import ingest_text
from personal_llm.tools import ToolRegistry
from personal_llm.tools.builtin import MemorySearchTool, RememberTool


def test_agent_answers_immediately_when_no_tool_needed(store, vectors, router):
    registry = ToolRegistry()
    router.script = [AgentStep(thought="I already know this.", final_answer="42")]
    agent = Agent(router, registry, store)

    result = agent.run("what is the answer?")

    assert result.succeeded
    assert result.final_answer == "42"
    assert len(result.steps) == 1
    assert result.steps[0].tool_name is None


def test_agent_calls_a_tool_then_answers(store, vectors, router):
    ingest_text(store, vectors, router, text="Zaid's favorite language is Python.", doc_id="doc1", source="test")
    registry = ToolRegistry()
    registry.register(MemorySearchTool(store, vectors, router))

    router.script = [
        AgentStep(
            thought="I should search memory.",
            tool=ToolInvocation(name="memory_search", args={"query": "favorite language"}),
        ),
        AgentStep(thought="Found it.", final_answer="Python"),
    ]
    agent = Agent(router, registry, store, allowed_permissions={"read_only"})

    result = agent.run("what is Zaid's favorite language?")

    assert result.succeeded
    assert result.final_answer == "Python"
    assert len(result.steps) == 2
    assert result.steps[0].tool_name == "memory_search"
    assert "python" in result.steps[0].observation.lower()


def test_agent_reports_permission_denial_as_observation(store, vectors, router):
    registry = ToolRegistry()
    registry.register(RememberTool(store))

    router.script = [
        AgentStep(thought="try to remember", tool=ToolInvocation(name="remember", args={"fact": "x"})),
        AgentStep(thought="ok, denied", final_answer="I couldn't save that."),
    ]
    agent = Agent(router, registry, store, allowed_permissions={"read_only"})

    result = agent.run("remember something")

    assert result.succeeded
    assert "ERROR" in result.steps[0].observation
    assert "read_write" in result.steps[0].observation


def test_agent_stops_after_max_steps(store, vectors, router):
    registry = ToolRegistry()
    registry.register(MemorySearchTool(store, vectors, router))
    router.script = [
        AgentStep(thought="loop", tool=ToolInvocation(name="memory_search", args={"query": "x"}))
        for _ in range(10)
    ]
    agent = Agent(router, registry, store, allowed_permissions={"read_only"}, max_steps=3)

    result = agent.run("loop forever")

    assert not result.succeeded
    assert len(result.steps) == 3
    assert "couldn't finish" in result.final_answer.lower()


def test_agent_falls_back_to_final_when_output_unparsed(store, vectors):
    class UnparsedRouter:
        def complete(self, messages, schema=None):
            from personal_llm.router.schemas import Completion

            return Completion(text="not json", parsed=None, provider="fake", model="fake")

    registry = ToolRegistry()
    agent = Agent(UnparsedRouter(), registry, store)

    result = agent.run("anything")

    assert result.succeeded
    assert result.final_answer == "not json"


def test_agent_logs_to_audit(store, vectors, router):
    registry = ToolRegistry()
    router.script = [AgentStep(thought="done", final_answer="ok")]
    agent = Agent(router, registry, store)

    agent.run("goal")

    rows = store.recent_audit(actor="agent")
    assert any(r["action"] == "final_answer" for r in rows)
