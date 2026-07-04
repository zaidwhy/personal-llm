"""Typer CLI - the fastest way to poke the engine from a terminal."""

from __future__ import annotations

from pathlib import Path

import typer

from personal_llm.agent import Agent
from personal_llm.config import get_settings
from personal_llm.engine import build_engine
from personal_llm.memory.consolidate import consolidate as run_consolidate
from personal_llm.memory.ingest import ingest_file
from personal_llm.memory.retrieve import semantic_search
from personal_llm.memory.types import MemoryRecord
from personal_llm.rag.pipeline import ask as rag_ask
from personal_llm.router.providers import RouterError
from personal_llm.tools import build_default_registry

app = typer.Typer(help="Personal LLM - your local-first memory + RAG engine.")


@app.command()
def ingest(paths: list[str] = typer.Argument(..., help="File(s) to ingest (.txt/.md/.pdf).")) -> None:
    """Ingest one or more files into memory."""
    engine = build_engine()
    for raw_path in paths:
        for path in sorted(Path().glob(raw_path)) if any(c in raw_path for c in "*?[") else [Path(raw_path)]:
            if not path.exists():
                typer.echo(f"skip (not found): {path}")
                continue
            result = ingest_file(engine.store, engine.vectors, engine.router, path)
            typer.echo(f"ingested {path}: {result.chunks_ingested} chunks, {result.kg_triples} KG triples")


@app.command()
def ask(question: str) -> None:
    """Ask a question grounded in ingested memory."""
    engine = build_engine()
    try:
        answer = rag_ask(engine.store, engine.vectors, engine.router, question)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(answer.text)
    if answer.sources:
        typer.echo("\nSources:")
        for src in answer.sources:
            typer.echo(f"  - {src.source}: {src.snippet[:100]}...")


@app.command()
def remember(fact: str, importance: float = 0.7) -> None:
    """Explicitly store a fact/preference (not tied to any file)."""
    engine = build_engine()
    record = MemoryRecord(kind="fact", content=fact, source="user", importance=importance)
    engine.store.add_memory(record)
    engine.store.log("user", "remember", {"content": fact})
    typer.echo(f"remembered ({record.id})")


@app.command()
def recall(query: str, k: int = 5) -> None:
    """Semantic search over memory without generating an answer."""
    engine = build_engine()
    results = semantic_search(engine.store, engine.vectors, engine.router, query, k=k)
    if not results:
        typer.echo("nothing found in memory.")
        return
    for r in results:
        typer.echo(f"[{r.rank_score:.2f}] ({r.source}) {r.text[:150]}")


@app.command()
def consolidate() -> None:
    """Run memory decay/dedup consolidation."""
    engine = build_engine()
    report = run_consolidate(engine.store)
    typer.echo(report.model_dump_json(indent=2))


@app.command()
def agent(
    goal: str,
    allow_network: bool = typer.Option(False, "--allow-network", help="Allow the web_fetch tool."),
    allow_write: bool = typer.Option(False, "--allow-write", help="Allow the remember (memory-write) tool."),
    max_steps: int = typer.Option(6, help="Stop after this many tool-call steps."),
) -> None:
    """Run the agent loop toward a goal, using tools under explicit permission."""
    engine = build_engine()
    settings = get_settings()
    registry = build_default_registry(engine.store, engine.vectors, engine.router, settings.personal_llm_workspace_dir)
    allowed = {"read_only"}
    if allow_network:
        allowed.add("network")
    if allow_write:
        allowed.add("read_write")

    runner = Agent(engine.router, registry, engine.store, allowed_permissions=allowed, max_steps=max_steps)
    try:
        result = runner.run(goal)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)

    for i, step in enumerate(result.steps, 1):
        typer.echo(f"[{i}] {step.thought}")
        if step.tool_name:
            snippet = (step.observation or "")[:150]
            typer.echo(f"    -> {step.tool_name}({step.tool_args}) => {snippet}")
    typer.echo(f"\n{result.final_answer}")
    if not result.succeeded:
        raise typer.Exit(code=1)


@app.command()
def stats() -> None:
    """Show memory/graph counts."""
    engine = build_engine()
    for key, value in engine.store.stats().items():
        typer.echo(f"{key}: {value}")


if __name__ == "__main__":
    app()
