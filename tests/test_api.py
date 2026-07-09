"""Gateway auth: shared token + Origin rejection (MASTER-FIX-PLAN.md Phase 3 item 12).

FakeRouter/store/vectors fixtures (conftest.py) keep this offline and keyless -
no network call, no API key, ever.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from personal_llm.engine import Engine
from personal_llm.interfaces import api
from personal_llm.voice import SpeechToText, TextToSpeech

TOKEN = "test-token"


def _fake_engine(store, vectors, router) -> Engine:
    return Engine(store=store, vectors=vectors, router=router, stt=SpeechToText(), tts=TextToSpeech())


def _client(monkeypatch, store, vectors, router):
    monkeypatch.setattr(api, "build_engine", lambda: _fake_engine(store, vectors, router))
    monkeypatch.setattr(api, "_load_or_create_gateway_token", lambda: TOKEN)
    return TestClient(api.app)


def test_tokenless_request_is_rejected(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.get("/stats")

    assert resp.status_code == 401


def test_wrong_token_is_rejected(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.get("/stats", headers={api.GATEWAY_TOKEN_HEADER: "not-the-token"})

    assert resp.status_code == 401


def test_correct_token_allows_stats(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.get("/stats", headers={api.GATEWAY_TOKEN_HEADER: TOKEN})

    assert resp.status_code == 200
    assert resp.json() == store.stats()


def test_origin_header_is_rejected_even_with_a_valid_token(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.get(
        "/stats",
        headers={api.GATEWAY_TOKEN_HEADER: TOKEN, "Origin": "https://evil.example"},
    )

    assert resp.status_code == 403


def test_ask_endpoint_requires_token(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.post("/ask", json={"question": "anything"})

    assert resp.status_code == 401


def test_ask_endpoint_round_trips_with_a_valid_token(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.post(
        "/ask",
        json={"question": "anything"},
        headers={api.GATEWAY_TOKEN_HEADER: TOKEN},
    )

    assert resp.status_code == 200
    assert "text" in resp.json()


def test_voice_ask_endpoint_requires_token(monkeypatch, store, vectors, router):
    client = _client(monkeypatch, store, vectors, router)

    resp = client.post("/voice/ask", files={"file": ("clip.wav", b"not real audio", "audio/wav")})

    assert resp.status_code == 401


def test_load_or_create_gateway_token_persists_across_calls(tmp_path, monkeypatch):
    token_path = tmp_path / "gateway_token"
    monkeypatch.setattr(api, "_gateway_token", None)
    monkeypatch.setattr(api, "get_settings", lambda: type("S", (), {"personal_llm_gateway_token_path": str(token_path)})())

    first = api._load_or_create_gateway_token()

    monkeypatch.setattr(api, "_gateway_token", None)
    second = api._load_or_create_gateway_token()

    assert first == second
    assert token_path.read_text().strip() == first
