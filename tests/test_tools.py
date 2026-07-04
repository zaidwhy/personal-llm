from __future__ import annotations

import pytest

from personal_llm.memory.types import MemoryRecord
from personal_llm.tools import ToolRegistry
from personal_llm.tools.builtin import (
    MemorySearchTool,
    ReadFileTool,
    RememberTool,
    WebFetchTool,
    build_default_registry,
)


def test_registry_rejects_unknown_tool():
    registry = ToolRegistry()
    result = registry.invoke("nope", {}, {"read_only"})
    assert not result.ok
    assert "unknown tool" in result.error


def test_registry_gates_by_permission(store):
    registry = ToolRegistry()
    registry.register(RememberTool(store))
    result = registry.invoke("remember", {"fact": "x"}, {"read_only"})
    assert not result.ok
    assert "read_write" in result.error


def test_registry_rejects_invalid_args(store):
    registry = ToolRegistry()
    registry.register(RememberTool(store))
    result = registry.invoke("remember", {}, {"read_write"})
    assert not result.ok
    assert "invalid arguments" in result.error


def test_memory_search_tool_finds_ingested_fact(store, vectors, router):
    from personal_llm.memory.ingest import ingest_text

    ingest_text(store, vectors, router, text="The sky is blue on a clear day.", doc_id="doc1", source="test")
    tool = MemorySearchTool(store, vectors, router)
    result = tool.run(tool.args_schema(query="sky color"))
    assert "sky" in result.lower()


def test_remember_tool_writes_a_fact(store):
    tool = RememberTool(store)
    output = tool.run(tool.args_schema(fact="favorite color is teal"))
    assert "remembered" in output
    facts = store.list_memories(kind="fact")
    assert any("teal" in f.content for f in facts)


def test_read_file_tool_reads_within_sandbox(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "note.txt").write_text("hello from sandbox", encoding="utf-8")
    tool = ReadFileTool(str(workspace))
    result = tool.run(tool.args_schema(path="note.txt"))
    assert result == "hello from sandbox"


def test_read_file_tool_blocks_path_traversal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    secret = tmp_path / "secret.txt"
    secret.write_text("top secret", encoding="utf-8")
    tool = ReadFileTool(str(workspace))
    from personal_llm.tools.base import ToolError

    with pytest.raises(ToolError, match="escapes"):
        tool.run(tool.args_schema(path="../secret.txt"))


def test_read_file_tool_missing_file_raises(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    tool = ReadFileTool(str(workspace))
    from personal_llm.tools.base import ToolError

    with pytest.raises(ToolError, match="no such file"):
        tool.run(tool.args_schema(path="ghost.txt"))


def test_web_fetch_tool_blocks_loopback():
    tool = WebFetchTool()
    from personal_llm.tools.base import ToolError

    with pytest.raises(ToolError, match="non-public"):
        tool.run(tool.args_schema(url="http://127.0.0.1:8080/"))


def test_web_fetch_tool_blocks_private_hostname():
    tool = WebFetchTool()
    from personal_llm.tools.base import ToolError

    with pytest.raises(ToolError, match="non-public"):
        tool.run(tool.args_schema(url="http://localhost/"))


def test_web_fetch_tool_rejects_non_http_scheme():
    tool = WebFetchTool()
    from personal_llm.tools.base import ToolError

    with pytest.raises(ToolError, match="http"):
        tool.run(tool.args_schema(url="ftp://example.com/file"))


def test_build_default_registry_has_all_four_tools(store, vectors, router, tmp_path):
    registry = build_default_registry(store, vectors, router, str(tmp_path / "workspace"))
    names = {spec["name"] for spec in registry.specs()}
    assert names == {"memory_search", "remember", "read_file", "web_fetch"}


def test_prompt_listing_mentions_permissions(store, vectors, router, tmp_path):
    registry = build_default_registry(store, vectors, router, str(tmp_path / "workspace"))
    listing = registry.prompt_listing()
    assert "[read_only]" in listing
    assert "[read_write]" in listing
    assert "[network]" in listing
