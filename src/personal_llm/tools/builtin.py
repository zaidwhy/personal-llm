"""The v0.2 safe tool set: memory (read + write), sandboxed file read, and a guarded
web fetch. Each covers a different permission tier (docs/TDD.md Security & Privacy;
docs/DECISIONS/0003-agent-tool-permissions.md)."""

from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel

from personal_llm.memory.retrieve import semantic_search
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.types import MemoryRecord
from personal_llm.memory.vectors import VectorStore
from personal_llm.router import ModelRouter

from .base import Tool, ToolError
from .registry import ToolRegistry

_MAX_FILE_CHARS = 20_000
_MAX_FETCH_CHARS = 4_000
_FETCH_TIMEOUT_SECONDS = 10.0


# --- memory_search (read_only) ---------------------------------------------------


class MemorySearchArgs(BaseModel):
    query: str
    k: int = 5


class MemorySearchTool(Tool):
    name = "memory_search"
    description = "Semantically search the user's own ingested notes and remembered facts."
    permission = "read_only"
    args_schema = MemorySearchArgs

    def __init__(self, store: MemoryStore, vectors: VectorStore, router: ModelRouter) -> None:
        self._store = store
        self._vectors = vectors
        self._router = router

    def run(self, args: MemorySearchArgs) -> str:
        results = semantic_search(self._store, self._vectors, self._router, args.query, k=args.k)
        if not results:
            return "No matching memories found."
        return "\n".join(f"[{r.rank_score:.2f}] ({r.source}) {r.text[:300]}" for r in results)


# --- remember (read_write) --------------------------------------------------------


class RememberArgs(BaseModel):
    fact: str
    importance: float = 0.6


class RememberTool(Tool):
    name = "remember"
    description = "Store a new fact or preference in long-term memory for future recall."
    permission = "read_write"
    args_schema = RememberArgs

    def __init__(self, store: MemoryStore) -> None:
        self._store = store

    def run(self, args: RememberArgs) -> str:
        record = MemoryRecord(kind="fact", content=args.fact, source="agent", importance=args.importance)
        self._store.add_memory(record)
        return f"remembered ({record.id})"


# --- read_file (read_only, sandboxed) ---------------------------------------------


class ReadFileArgs(BaseModel):
    path: str


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a text file from the local workspace sandbox (data/workspace)."
    permission = "read_only"
    args_schema = ReadFileArgs

    def __init__(self, workspace_dir: str) -> None:
        self._root = Path(workspace_dir).resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def run(self, args: ReadFileArgs) -> str:
        candidate = (self._root / args.path).resolve()
        if self._root not in candidate.parents and candidate != self._root:
            raise ToolError(f"path '{args.path}' escapes the workspace sandbox")
        if not candidate.is_file():
            raise ToolError(f"no such file in workspace: '{args.path}'")
        text = candidate.read_text(encoding="utf-8", errors="replace")
        return text[:_MAX_FILE_CHARS]


# --- web_fetch (network, SSRF-guarded) --------------------------------------------


class WebFetchArgs(BaseModel):
    url: str


def _reject_private_targets(hostname: str) -> None:
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ToolError(f"could not resolve host '{hostname}': {exc}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ToolError(f"refusing to fetch '{hostname}': resolves to a non-public address ({ip})")


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a public web page over HTTP(S) and return its text content."
    permission = "network"
    args_schema = WebFetchArgs

    def run(self, args: WebFetchArgs) -> str:
        import httpx

        parsed = urlparse(args.url)
        if parsed.scheme not in ("http", "https"):
            raise ToolError("only http:// and https:// URLs are allowed")
        if not parsed.hostname:
            raise ToolError("URL has no hostname")
        _reject_private_targets(parsed.hostname)

        try:
            response = httpx.get(
                args.url, timeout=_FETCH_TIMEOUT_SECONDS, follow_redirects=False, headers={"User-Agent": "personal-llm-agent/0.1"}
            )
        except httpx.HTTPError as exc:
            raise ToolError(f"fetch failed: {exc}")

        if response.is_redirect:
            raise ToolError(f"'{args.url}' returned a redirect; refusing to follow it automatically")
        if response.status_code >= 400:
            raise ToolError(f"'{args.url}' returned HTTP {response.status_code}")

        text = re.sub(r"<[^>]+>", " ", response.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:_MAX_FETCH_CHARS]


def build_default_registry(store: MemoryStore, vectors: VectorStore, router: ModelRouter, workspace_dir: str) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(MemorySearchTool(store, vectors, router))
    registry.register(RememberTool(store))
    registry.register(ReadFileTool(workspace_dir))
    registry.register(WebFetchTool())
    return registry
