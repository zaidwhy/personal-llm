"""Local text-to-speech via pyttsx3 - uses the OS's native voices (SAPI5 on Windows),
fully offline, no API key, no model download."""

from __future__ import annotations

from pathlib import Path


class TextToSpeech:
    def synthesize(self, text: str, out_path: str) -> str:
        import pyttsx3

        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        engine = pyttsx3.init()
        engine.save_to_file(text, out_path)
        engine.runAndWait()
        return out_path


def synthesize(text: str, out_path: str) -> str:
    return TextToSpeech().synthesize(text, out_path)
