"""Shared bootstrap so CLI, API, and Streamlit all wire up the same engine the same way."""

from __future__ import annotations

from dataclasses import dataclass

from personal_llm.config import get_settings
from personal_llm.memory.store import MemoryStore
from personal_llm.memory.vectors import VectorStore
from personal_llm.router import ModelRouter
from personal_llm.voice import SpeechToText, TextToSpeech


@dataclass
class Engine:
    store: MemoryStore
    vectors: VectorStore
    router: ModelRouter
    stt: SpeechToText
    tts: TextToSpeech


_engine: Engine | None = None


def build_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = Engine(
            store=MemoryStore(settings.personal_llm_db_path),
            vectors=VectorStore(settings.personal_llm_chroma_dir),
            router=ModelRouter(),
            stt=SpeechToText(),
            tts=TextToSpeech(),
        )
    return _engine
