from __future__ import annotations

from personal_llm.voice.stt import SpeechToText
from personal_llm.voice.tts import TextToSpeech


class _FakeSegment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeWhisperModel:
    instances = 0

    def __init__(self, model_size, device=None, compute_type=None) -> None:
        _FakeWhisperModel.instances += 1
        self.model_size = model_size

    def transcribe(self, audio_path):
        return [_FakeSegment(" hello "), _FakeSegment("world ")], {"language": "en"}


def test_transcribe_joins_segments_and_strips(monkeypatch):
    monkeypatch.setattr("faster_whisper.WhisperModel", _FakeWhisperModel)
    stt = SpeechToText(model_size="tiny")

    text = stt.transcribe("audio.wav")

    assert text == "hello world"


def test_transcribe_lazy_loads_model_once(monkeypatch):
    _FakeWhisperModel.instances = 0
    monkeypatch.setattr("faster_whisper.WhisperModel", _FakeWhisperModel)
    stt = SpeechToText(model_size="tiny")

    stt.transcribe("a.wav")
    stt.transcribe("b.wav")

    assert _FakeWhisperModel.instances == 1


def test_transcribe_uses_configured_model_size(monkeypatch):
    monkeypatch.setattr("faster_whisper.WhisperModel", _FakeWhisperModel)
    stt = SpeechToText(model_size="small")

    stt.transcribe("a.wav")

    assert stt._model.model_size == "small"


class _FakeTtsEngine:
    def __init__(self) -> None:
        self.saved: tuple[str, str] | None = None
        self.ran = False

    def save_to_file(self, text, path):
        self.saved = (text, path)

    def runAndWait(self):
        self.ran = True


def test_synthesize_saves_to_file_and_runs(monkeypatch, tmp_path):
    fake_engine = _FakeTtsEngine()
    monkeypatch.setattr("pyttsx3.init", lambda: fake_engine)
    out_path = str(tmp_path / "out.wav")

    result = TextToSpeech().synthesize("hello there", out_path)

    assert result == out_path
    assert fake_engine.saved == ("hello there", out_path)
    assert fake_engine.ran is True


def test_synthesize_creates_parent_directory(monkeypatch, tmp_path):
    monkeypatch.setattr("pyttsx3.init", lambda: _FakeTtsEngine())
    out_path = tmp_path / "nested" / "dir" / "out.wav"

    TextToSpeech().synthesize("hi", str(out_path))

    assert out_path.parent.is_dir()
