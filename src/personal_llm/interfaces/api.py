"""FastAPI surface - the stable HTTP API non-Python callers use (docs/TDD.md section 8)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from personal_llm.engine import build_engine
from personal_llm.memory.ingest import IngestResult, ingest_text
from personal_llm.memory.retrieve import RetrievedChunk, semantic_search
from personal_llm.memory.types import MemoryRecord
from personal_llm.rag.pipeline import Answer, ask as rag_ask
from personal_llm.router.providers import RouterError

app = FastAPI(title="Personal LLM", version="0.1.0")


class IngestRequest(BaseModel):
    text: str
    doc_id: str
    source: str = "api"


class AskRequest(BaseModel):
    question: str
    k: int | None = None


class RememberRequest(BaseModel):
    fact: str
    importance: float = 0.7


@app.post("/ingest", response_model=IngestResult)
def ingest_endpoint(req: IngestRequest) -> IngestResult:
    engine = build_engine()
    return ingest_text(engine.store, engine.vectors, engine.router, text=req.text, doc_id=req.doc_id, source=req.source)


@app.post("/ask", response_model=Answer)
def ask_endpoint(req: AskRequest) -> Answer:
    engine = build_engine()
    try:
        return rag_ask(engine.store, engine.vectors, engine.router, req.question, k=req.k)
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


@app.get("/stats")
def stats_endpoint() -> dict:
    engine = build_engine()
    return engine.store.stats()
