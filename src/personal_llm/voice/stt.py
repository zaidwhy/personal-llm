"""Local speech-to-text via faster-whisper - offline, free, no API key. Same lazy-load-the-
heavy-model-on-first-use pattern as LocalEmbedder in router/providers.py."""

from __future__ import annotations

from personal_llm.config import get_settings


class SpeechToText:
    def __init__(self, model_size: str | None = None) -> None:
        self._settings = get_settings()
        self._model_size = model_size or self._settings.whisper_model_size
        self._model = None

    def _get_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio_path: str) -> str:
        model = self._get_model()
        segments, _info = model.transcribe(audio_path)
        return " ".join(segment.text.strip() for segment in segments).strip()


def transcribe_audio(audio_path: str, model_size: str | None = None) -> str:
    return SpeechToText(model_size).transcribe(audio_path)
