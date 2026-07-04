"""Concrete providers behind the router. Only this module talks to the network."""

from __future__ import annotations

import json
import time
from typing import Protocol

from pydantic import BaseModel

from personal_llm.config import get_settings

from .schemas import Completion, Message

_MAX_RETRIES = 3


class RouterError(Exception):
    """User-facing error the caller can display verbatim."""


class ChatProvider(Protocol):
    name: str

    def complete(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Completion: ...

    def is_available(self) -> bool: ...


def _messages_to_gemini(messages: list[Message]) -> tuple[str, str]:
    system = "\n".join(m.content for m in messages if m.role == "system")
    convo = "\n\n".join(f"{m.role}: {m.content}" for m in messages if m.role != "system")
    return system, convo


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        self._settings = get_settings()
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            if not self._settings.gemini_api_key:
                raise RouterError(
                    "No GEMINI_API_KEY found. Get a free key at https://aistudio.google.com/apikey "
                    "and add it to .env as GEMINI_API_KEY=your-key-here."
                )
            self._client = genai.Client(api_key=self._settings.gemini_api_key)
        return self._client

    def is_available(self) -> bool:
        return bool(self._settings.gemini_api_key)

    def complete(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Completion:
        from google.genai import errors as genai_errors
        from google.genai import types

        client = self._get_client()
        system, convo = _messages_to_gemini(messages)
        config_kwargs: dict = {"system_instruction": system, "temperature": 0.3}
        if schema is not None:
            config_kwargs["response_mime_type"] = "application/json"
            config_kwargs["response_schema"] = schema

        last_err: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                response = client.models.generate_content(
                    model=self._settings.gemini_model,
                    contents=convo,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                parsed = getattr(response, "parsed", None) if schema is not None else None
                return Completion(
                    text=response.text or "",
                    parsed=parsed,
                    provider=self.name,
                    model=self._settings.gemini_model,
                )
            except genai_errors.ClientError as exc:
                if getattr(exc, "code", None) != 429:
                    raise RouterError(f"Gemini rejected the request: {getattr(exc, 'message', exc)}")
                last_err = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(4 * (attempt + 1))
            except genai_errors.ServerError as exc:
                last_err = exc
                if attempt < _MAX_RETRIES - 1:
                    time.sleep(4 * (attempt + 1))
        raise RouterError(f"Gemini is unavailable after {_MAX_RETRIES} attempts: {last_err}")

    def describe_image(self, image_bytes: bytes, mime_type: str, question: str | None = None) -> str:
        from google.genai import errors as genai_errors
        from google.genai import types

        client = self._get_client()
        prompt = question or "Describe this image in detail."
        try:
            response = client.models.generate_content(
                model=self._settings.gemini_model,
                contents=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type), prompt],
            )
            return response.text or ""
        except (genai_errors.ClientError, genai_errors.ServerError) as exc:
            raise RouterError(f"Gemini vision request failed: {getattr(exc, 'message', exc)}")


class OllamaProvider:
    name = "ollama"

    def __init__(self) -> None:
        self._settings = get_settings()

    def is_available(self) -> bool:
        try:
            import httpx

            resp = httpx.get(f"{self._settings.ollama_host}/api/tags", timeout=1.0)
            return resp.status_code == 200
        except Exception:
            return False

    def complete(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Completion:
        import ollama

        client = ollama.Client(host=self._settings.ollama_host)
        kwargs: dict = {}
        if schema is not None:
            kwargs["format"] = schema.model_json_schema()

        try:
            response = client.chat(
                model=self._settings.ollama_model,
                messages=[m.model_dump() for m in messages],
                **kwargs,
            )
        except Exception as exc:
            raise RouterError(f"Ollama call failed: {exc}")

        text = response["message"]["content"]
        parsed = None
        if schema is not None:
            try:
                parsed = schema(**json.loads(text))
            except (json.JSONDecodeError, ValueError):
                parsed = None
        return Completion(text=text, parsed=parsed, provider=self.name, model=self._settings.ollama_model)


class LocalEmbedder:
    """Free, offline embeddings via sentence-transformers. Loaded lazily (slow import)."""

    def __init__(self) -> None:
        self._settings = get_settings()
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._settings.embedding_model)
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        vectors = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return vectors.tolist()
