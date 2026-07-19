"""Typer CLI - the fastest way to poke the engine from a terminal."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from personal_llm import __version__
from personal_llm.agent import Agent
from personal_llm.config import get_settings
from personal_llm.engine import build_engine
from personal_llm.eval import run_eval
from personal_llm.eval.cases import builtin_cases
from personal_llm.integrations import ExternalItem, sync_external_items
from personal_llm.memory.consolidate import consolidate as run_consolidate
from personal_llm.memory.ingest import ingest_file
from personal_llm.memory.interest_trends import detect_interest_trends_in_store
from personal_llm.memory.retrieve import semantic_search
from personal_llm.memory.types import MemoryRecord
from personal_llm.rag.pipeline import ask as rag_ask
from personal_llm.review.weekly import generate_review
from personal_llm.router.providers import RouterError
from personal_llm.tools import build_default_registry
from personal_llm.vision import VisionError

app = typer.Typer(help="Personal LLM - your local-first memory + RAG engine.")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"personal-llm {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False, "--version", callback=_version_callback, is_eager=True, help="Show the version and exit."
    ),
) -> None:
    pass


@app.command()
def ingest(paths: list[str] = typer.Argument(..., help="File(s) to ingest (.txt/.md/.pdf/image via OCR).")) -> None:
    """Ingest one or more files into memory."""
    engine = build_engine()
    for raw_path in paths:
        for path in sorted(Path().glob(raw_path)) if any(c in raw_path for c in "*?[") else [Path(raw_path)]:
            if not path.exists():
                typer.echo(f"skip (not found): {path}")
                continue
            try:
                result = ingest_file(engine.store, engine.vectors, engine.router, path)
            except VisionError as exc:
                typer.echo(f"skip ({path}): {exc}")
                continue
            typer.echo(f"ingested {path}: {result.chunks_ingested} chunks, {result.kg_triples} KG triples")


@app.command()
def ask(
    question: str,
    verify: bool = typer.Option(False, "--verify", help="Cross-check across all available providers."),
) -> None:
    """Ask a question grounded in ingested memory."""
    engine = build_engine()
    try:
        answer = rag_ask(engine.store, engine.vectors, engine.router, question, verify=verify)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(answer.text)
    if answer.disagreement:
        typer.echo("\n[!] Providers disagreed on this answer:")
        for alt in answer.alternate_texts:
            typer.echo(f"  - {alt[:150]}")
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
def review(days: int = typer.Option(7, help="How many days back counts as 'recent'.")) -> None:
    """Proactive review: recent activity plus important items you haven't revisited."""
    engine = build_engine()
    try:
        report = generate_review(engine.store, engine.router, days=days)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)

    typer.echo(f"Review ({report.days}d): {report.recent_count} recent, {report.forgotten_count} forgotten-but-important\n")
    if report.insights.highlights:
        typer.echo("Highlights:")
        for item in report.insights.highlights:
            typer.echo(f"  - {item}")
    if report.insights.forgotten_worth_revisiting:
        typer.echo("\nWorth revisiting:")
        for item in report.insights.forgotten_worth_revisiting:
            typer.echo(f"  - {item}")
    if report.insights.suggested_actions:
        typer.echo("\nSuggested actions:")
        for item in report.insights.suggested_actions:
            typer.echo(f"  - {item}")


@app.command()
def trends(
    window_days: float = typer.Option(7.0, help="Size of the 'recent' and 'previous' comparison windows, in days."),
    k: int = typer.Option(10, help="Number of keywords to show."),
) -> None:
    """Interest-trend detector: keywords said much more (or less) in the recent
    window than the equal-length window right before it."""
    engine = build_engine()
    result = detect_interest_trends_in_store(engine.store, window_days=window_days, k=k)
    if not result:
        typer.echo("Not enough ingestion history yet to detect a trend.")
        return
    for trend in result:
        arrow = "^" if trend.delta > 0 else "v" if trend.delta < 0 else "="
        typer.echo(f"[{arrow}{abs(trend.delta)}] {trend.keyword} (recent {trend.recent_count}, previous {trend.previous_count})")


@app.command()
def eval() -> None:
    """Run the prompt-regression eval suite (offline, no engine/API key needed) and
    report pass/fail per case; exits non-zero if any case failed."""
    report = run_eval(builtin_cases())
    for result in report.results:
        if result.error is not None:
            typer.echo(f"[ERROR] {result.name}: {result.error}")
        elif result.passed:
            typer.echo(f"[PASS]  {result.name}")
        else:
            typer.echo(f"[FAIL]  {result.name}")
            for failure in result.failures:
                typer.echo(f"          - {failure}")
    typer.echo(f"\n{report.summary}")
    if not report.passed:
        raise typer.Exit(code=1)


@app.command(name="ingest-external")
def ingest_external(
    path: str = typer.Argument(..., help="JSON file: a list of {source, external_id, title, content, url?} items."),
) -> None:
    """Ingest pre-fetched external items (e.g. Gmail/Drive content fetched via Claude Code's
    own MCP connectors - see docs/DECISIONS/0005). This command never fetches anything itself
    and has no credentials; point it at a JSON file someone/something else produced."""
    engine = build_engine()
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    items = [ExternalItem(**entry) for entry in raw]
    result = sync_external_items(engine.store, engine.vectors, engine.router, items)
    typer.echo(f"ingested {result.ingested}, skipped {result.skipped_existing} already-synced")


@app.command()
def transcribe(audio_path: str) -> None:
    """Transcribe an audio file to text (local Whisper - offline, no API key)."""
    engine = build_engine()
    typer.echo(engine.stt.transcribe(audio_path))


@app.command(name="ask-voice")
def ask_voice(
    audio_path: str,
    verify: bool = typer.Option(False, "--verify", help="Cross-check across all available providers."),
    speak: bool = typer.Option(False, "--speak", help="Also synthesize the answer to a wav file."),
) -> None:
    """Transcribe an audio question, then answer it grounded in memory."""
    engine = build_engine()
    settings = get_settings()
    question = engine.stt.transcribe(audio_path)
    typer.echo(f"heard: {question}\n")
    try:
        answer = rag_ask(engine.store, engine.vectors, engine.router, question, verify=verify)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(answer.text)
    if speak:
        out_path = str(Path(settings.personal_llm_voice_dir) / "answer.wav")
        engine.tts.synthesize(answer.text, out_path)
        typer.echo(f"\n(spoken answer saved to {out_path})")


@app.command(name="describe-image")
def describe_image(image_path: str, question: str | None = typer.Argument(None)) -> None:
    """Ask Gemini about an image (vision Q&A - requires GEMINI_API_KEY; Ollama has no vision path here)."""
    engine = build_engine()
    try:
        description = engine.router.describe_image(image_path, question)
    except RouterError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(description)


@app.command()
def doctor() -> None:
    """Check environment health - version, data paths, provider status. Run this first."""
    engine = build_engine()
    settings = get_settings()

    typer.echo(f"personal-llm {__version__}")
    typer.echo(f"data dir:   {settings.personal_llm_data_dir}")
    typer.echo(f"db path:    {settings.personal_llm_db_path}")
    typer.echo(f"chroma dir: {settings.personal_llm_chroma_dir}")
    typer.echo()

    status = engine.router.provider_status()
    for name, available in status.items():
        typer.echo(f"provider {name}: {'available' if available else 'not configured'}")
    if not any(status.values()):
        typer.echo("\n[!] No chat provider available - set GEMINI_API_KEY in .env, or run Ollama locally.")

    typer.echo()
    stats_report = engine.store.stats()
    typer.echo(
        f"memories: {stats_report['memories']} ({stats_report['archived_memories']} archived), "
        f"chunks: {stats_report['chunks']}, kg_nodes: {stats_report['kg_nodes']}, kg_edges: {stats_report['kg_edges']}"
    )


@app.command()
def stats() -> None:
    """Show memory/graph counts."""
    engine = build_engine()
    for key, value in engine.store.stats().items():
        typer.echo(f"{key}: {value}")


if __name__ == "__main__":
    app()
