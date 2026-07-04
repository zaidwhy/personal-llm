"""Local OCR via pytesseract - offline, free, but needs the Tesseract-OCR binary installed
separately (exactly like Ollama: an optional external dependency, not something pip alone
can provide). Degrades with a clear, actionable error rather than a raw stack trace."""

from __future__ import annotations


class VisionError(Exception):
    """Raised when OCR can't run - most commonly, Tesseract isn't installed."""


def extract_text_from_image(image_path: str) -> str:
    import pytesseract
    from PIL import Image

    try:
        image = Image.open(image_path)
    except Exception as exc:
        raise VisionError(f"could not open image '{image_path}': {exc}")

    try:
        return pytesseract.image_to_string(image).strip()
    except pytesseract.TesseractNotFoundError:
        raise VisionError(
            "Tesseract OCR is not installed. pytesseract is only a Python wrapper - it needs "
            "the actual tesseract binary on PATH. Install it separately, e.g. "
            "https://github.com/UB-Mannheim/tesseract/wiki on Windows, then retry."
        )
