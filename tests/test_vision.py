from __future__ import annotations

import pytest

from personal_llm.router.providers import RouterError
from personal_llm.router.router import ModelRouter
from personal_llm.vision.ocr import VisionError, extract_text_from_image


class _FakeImage:
    pass


def test_extract_text_from_image_strips_result(monkeypatch):
    monkeypatch.setattr("PIL.Image.open", lambda path: _FakeImage())
    monkeypatch.setattr("pytesseract.image_to_string", lambda image: "  hello world  \n")

    text = extract_text_from_image("fake.png")

    assert text == "hello world"


def test_extract_text_from_image_raises_on_missing_file():
    with pytest.raises(VisionError, match="could not open image"):
        extract_text_from_image("this_file_does_not_exist.png")


def test_extract_text_from_image_raises_clear_error_when_tesseract_missing(monkeypatch):
    import pytesseract

    def _raise(image):
        raise pytesseract.TesseractNotFoundError()

    monkeypatch.setattr("PIL.Image.open", lambda path: _FakeImage())
    monkeypatch.setattr("pytesseract.image_to_string", _raise)

    with pytest.raises(VisionError, match="Tesseract OCR is not installed"):
        extract_text_from_image("fake.png")


class _FakeGeminiProvider:
    name = "gemini"

    def __init__(self, available=True, raises=False):
        self._available = available
        self._raises = raises
        self.calls = []

    def is_available(self):
        return self._available

    def describe_image(self, image_bytes, mime_type, question=None):
        self.calls.append((image_bytes, mime_type, question))
        if self._raises:
            raise RouterError("gemini vision failed")
        return "a description"


def test_describe_image_delegates_to_gemini(tmp_path):
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"fake-bytes")
    router = ModelRouter(chat_providers=[])
    router._gemini = _FakeGeminiProvider(available=True)

    result = router.describe_image(str(image_path), "what is this?")

    assert result == "a description"
    assert router._gemini.calls[0][1] == "image/png"
    assert router._gemini.calls[0][2] == "what is this?"


def test_describe_image_raises_when_gemini_not_configured(tmp_path):
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"fake-bytes")
    router = ModelRouter(chat_providers=[])
    router._gemini = _FakeGeminiProvider(available=False)

    with pytest.raises(RouterError, match="No GEMINI_API_KEY"):
        router.describe_image(str(image_path))


def test_describe_image_propagates_gemini_error(tmp_path):
    image_path = tmp_path / "photo.png"
    image_path.write_bytes(b"fake-bytes")
    router = ModelRouter(chat_providers=[])
    router._gemini = _FakeGeminiProvider(available=True, raises=True)

    with pytest.raises(RouterError, match="gemini vision failed"):
        router.describe_image(str(image_path))
