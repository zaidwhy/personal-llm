"""FastAPI surface - the stable HTTP API non-Python callers use (docs/TDD.md section 8)."""

from __future__ import annotations

import secrets
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from personal_llm import __version__
from personal_llm.agent import Agent, AgentResult
from personal_llm.config import get_settings
from personal_llm.engine import build_engine
from personal_llm.integrations import ExternalItem, SyncResult, sync_external_items
from personal_llm.memory.ingest import IngestResult, ingest_text
from personal_llm.memory.retrieve import RetrievedChunk, semantic_search
from personal_llm.memory.types import MemoryRecord
from personal_llm.rag.pipeline import Answer, ask as rag_ask
from personal_llm.review.weekly import ReviewReport, generate_review
from personal_llm.router.providers import RouterError
from personal_llm.tools import build_default_registry
from personal_llm.vision import VisionError

app = FastAPI(title="Personal LLM", version=__version__)

GATEWAY_TOKEN_HEADER = "x-dreamos-token"
_gateway_token: str | None = None


def _load_or_create_gateway_token() -> str:
    """Shared secret DreamOS (or any other local caller) must send back on every request.

    Generated once and persisted to disk so it survives a gateway restart without the
    caller needing to re-pair.
    """
    global _gateway_token
    if _gateway_token is not None:
        return _gateway_token
    path = Path(get_settings().personal_llm_gateway_token_path)
    existing = path.read_text().strip() if path.exists() else ""
    if existing:
        _gateway_token = existing
    else:
        _gateway_token = secrets.token_hex(32)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_gateway_token)
    return _gateway_token


@app.middleware("http")
async def gateway_auth(request: Request, call_next):
    """CSRF hardening (MASTER-FIX-PLAN.md S3 / Phase 3 item 12).

    Multipart and form-encoded POSTs are reachable cross-origin without a CORS
    preflight, so a browser page could otherwise submit them straight to this
    gateway. Any request carrying an Origin header - which every real browser
    request does, and no local non-browser caller does - is rejected outright,
    and every request must also present the shared token.
    """
    if "origin" in request.headers:
        return JSONResponse(status_code=403, content={"detail": "Cross-origin requests are not allowed."})
    if request.headers.get(GATEWAY_TOKEN_HEADER) != _load_or_create_gateway_token():
        return JSONResponse(status_code=401, content={"detail": "Missing or invalid X-DreamOS-Token."})
    return await call_next(request)


async def _save_upload_to_temp(upload: UploadFile) -> str:
    suffix = Path(upload.filename or "upload").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await upload.read())
        return tmp.name


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


class IntegrationsSyncRequest(BaseModel):
    items: list[ExternalItem]


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


@app.post("/integrations/sync", response_model=SyncResult)
def integrations_sync_endpoint(req: IntegrationsSyncRequest) -> SyncResult:
    engine = build_engine()
    return sync_external_items(engine.store, engine.vectors, engine.router, req.items)


def _transcribe_or_400(engine, tmp_path: str) -> str:
    """Undecodable or silent audio must be a clear 400, never a crashed request.

    The av.open pre-check matters: feeding non-audio bytes straight into whisper can
    hard-crash the worker process (not a catchable exception), so validate first.
    """
    try:
        import av

        with av.open(tmp_path) as container:
            if not container.streams.audio:
                raise ValueError("no audio stream")
    except Exception:
        raise HTTPException(
            status_code=400,
            detail="That did not decode as audio - record a bit longer and try again.",
        )
    try:
        text = engine.stt.transcribe(tmp_path)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not decode the audio - record a bit longer and try again. ({type(exc).__name__})",
        )
    if not text.strip():
        raise HTTPException(status_code=400, detail="I heard nothing - hold to talk, speak, then release.")
    return text


@app.post("/voice/transcribe")
async def voice_transcribe_endpoint(file: UploadFile = File(...)) -> dict:
    engine = build_engine()
    tmp_path = await _save_upload_to_temp(file)
    try:
        return {"text": _transcribe_or_400(engine, tmp_path)}
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/voice/ask", response_model=Answer)
async def voice_ask_endpoint(file: UploadFile = File(...), verify: bool = False) -> Answer:
    engine = build_engine()
    tmp_path = await _save_upload_to_temp(file)
    try:
        question = _transcribe_or_400(engine, tmp_path)
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    try:
        return rag_ask(engine.store, engine.vectors, engine.router, question, verify=verify)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@app.post("/vision/describe")
async def vision_describe_endpoint(file: UploadFile = File(...), question: str | None = None) -> dict:
    engine = build_engine()
    tmp_path = await _save_upload_to_temp(file)
    try:
        description = engine.router.describe_image(tmp_path, question)
    except RouterError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return {"description": description}


@app.post("/vision/ingest")
async def vision_ingest_endpoint(file: UploadFile = File(...), doc_id: str | None = None) -> IngestResult:
    engine = build_engine()
    tmp_path = await _save_upload_to_temp(file)
    try:
        from personal_llm.vision.ocr import extract_text_from_image

        text = extract_text_from_image(tmp_path)
    except VisionError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    finally:
        Path(tmp_path).unlink(missing_ok=True)
    return ingest_text(
        engine.store, engine.vectors, engine.router,
        text=text, doc_id=doc_id or (file.filename or "image"), source=file.filename or "image",
    )


@app.get("/stats")
def stats_endpoint() -> dict:
    engine = build_engine()
    return engine.store.stats()
