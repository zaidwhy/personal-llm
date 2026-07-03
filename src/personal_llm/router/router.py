"""The one place the rest of the engine calls out to a model.

Hybrid local+cloud (ADR 0002): embeddings are always local (free, offline).
Chat completion prefers a healthy local Ollama if configured, else Gemini.
"""

from __future__ import annotations

from pydantic import BaseModel

from .providers import ChatProvider, GeminiProvider, LocalEmbedder, OllamaProvider, RouterError
from .schemas import Completion, Message

__all__ = ["ModelRouter", "RouterError"]


class ModelRouter:
    def __init__(
        self,
        chat_providers: list[ChatProvider] | None = None,
        embedder: LocalEmbedder | None = None,
    ) -> None:
        self._ollama = OllamaProvider()
        self._gemini = GeminiProvider()
        self._chat_providers = chat_providers if chat_providers is not None else [self._ollama, self._gemini]
        self._embedder = embedder or LocalEmbedder()
        self._ollama_healthy: bool | None = None

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._embedder.embed(texts)

    def complete(self, messages: list[Message], schema: type[BaseModel] | None = None) -> Completion:
        errors: list[str] = []
        for provider in self._chat_providers:
            if provider.name == "ollama" and self._ollama_healthy is None:
                self._ollama_healthy = provider.is_available()
            if provider.name == "ollama" and not self._ollama_healthy:
                continue
            if provider.name != "ollama" and not provider.is_available():
                errors.append(f"{provider.name}: not configured")
                continue
            try:
                return provider.complete(messages, schema=schema)
            except RouterError as exc:
                errors.append(f"{provider.name}: {exc}")
                continue
        raise RouterError(
            "No chat provider available. " + ("; ".join(errors) if errors else "Configure GEMINI_API_KEY or run Ollama.")
        )
