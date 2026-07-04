"""FastAPI surface - the stable HTTP API non-Python callers use (docs/TDD.md section 8)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from personal_llm.agent import Agent, AgentResult
from personal_llm.config import get_settings
from personal_llm.engine import build_engine
from personal_llm.memory.ingest import IngestResult, ingest_text
from personal_llm.memory.retrieve import RetrievedChunk, semantic_search
from personal_llm.memory.types import MemoryRecord
from personal_llm.rag.pipeline import Answer, ask as rag_ask
from personal_llm.review.weekly import ReviewReport, generate_review
from personal_llm.router.providers import RouterError
from personal_llm.tools import build_default_registry

app = FastAPI(title="Personal LLM", version="0.1.0")


class IngestRequest(BaseModel):
    text: str
    doc_id: str
    source: str = "api"


class AskRequest(BaseModel):
    question: str
    k: int | None = None
    verify: bool = False


class RememberRequest(BaseModel):
    fact: str
    importance: float = 0.7


class AgentRunRequest(BaseModel):
    goal: str
    allow_network: bool = False
    allow_write: bool = False
    max_steps: int = 6


class ReviewRequest(BaseModel):
    days: int = 7


@app.post("/ingest", response_model=IngestResult)
def ingest_endpoint(req: IngestRequest) -> IngestResult:
    engine = build_engine()
    return ingest_text(engine.store, engine.vectors, engine.router, text=req.text, doc_id=req.doc_id, source=req.source)


@app.post("/ask", response_model=Answer)
def ask_endpoint(req: AskRequest) -> Answer:
    engine = build_engine()
    try:
        return rag_ask(engine.store, engine.vectors, engine.router, req.question, k=req.k, verify=req.verify)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/memory/remember")
def remember_endpoint(req: RememberRequest) -> dict:
    engine = build_engine()
    record = MemoryRecord(kind="fact", content=req.fact, source="user", importance=req.importance)
    engine.store.add_memory(record)
    return {"id": record.id}


@app.get("/memory/recall", response_model=list[RetrievedChunk])
def recall_endpoint(q: str, k: int = 5) -> list[RetrievedChunk]:
    engine = build_engine()
    return semantic_search(engine.store, engine.vectors, engine.router, q, k=k)


@app.post("/agent/run", response_model=AgentResult)
def agent_run_endpoint(req: AgentRunRequest) -> AgentResult:
    engine = build_engine()
    settings = get_settings()
    registry = build_default_registry(engine.store, engine.vectors, engine.router, settings.personal_llm_workspace_dir)
    allowed = {"read_only"}
    if req.allow_network:
        allowed.add("network")
    if req.allow_write:
        allowed.add("read_write")
    runner = Agent(engine.router, registry, engine.store, allowed_permissions=allowed, max_steps=req.max_steps)
    try:
        return runner.run(req.goal)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/review/run", response_model=ReviewReport)
def review_endpoint(req: ReviewRequest) -> ReviewReport:
    engine = build_engine()
    try:
        return generate_review(engine.store, engine.router, days=req.days)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.get("/stats")
def stats_endpoint() -> dict:
    engine = build_engine()
    return engine.store.stats()
