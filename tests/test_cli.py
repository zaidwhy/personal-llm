from __future__ import annotations

from typer.testing import CliRunner

from personal_llm import __version__
from personal_llm.engine import Engine
from personal_llm.interfaces import cli
from personal_llm.voice import SpeechToText, TextToSpeech

runner = CliRunner()


def _fake_engine(store, vectors, router) -> Engine:
    return Engine(store=store, vectors=vectors, router=router, stt=SpeechToText(), tts=TextToSpeech())


def test_version_flag_prints_version_and_exits():
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_doctor_reports_provider_status_and_stats(monkeypatch, store, vectors, router):
    monkeypatch.setattr(cli, "build_engine", lambda: _fake_engine(store, vectors, router))

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert f"personal-llm {__version__}" in result.output
    assert "provider fake: available" in result.output
    assert "memories:" in result.output


def test_doctor_warns_when_no_provider_available(monkeypatch, store, vectors, router):
    router.provider_status = lambda: {"gemini": False, "ollama": False}
    monkeypatch.setattr(cli, "build_engine", lambda: _fake_engine(store, vectors, router))

    result = runner.invoke(cli.app, ["doctor"])

    assert result.exit_code == 0
    assert "No chat provider available" in result.output
