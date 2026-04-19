"""Tesseract OCR wrapper for scanned PDFs.

Invoked by the SegmentAgent when a PDF page has < OCR_MIN_TEXT_CHARS chars of
extracted text (default 40). Returns per-page text + per-page confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..core import get_logger, settings


log = get_logger("ocr")


@dataclass
class OCRResult:
    text: str
    page_offsets: list[tuple[int, int]] = field(default_factory=list)
    page_confidences: list[float] = field(default_factory=list)


def ocr_pdf(path: Path) -> OCRResult:
    if not settings.ocr_enabled:
        return OCRResult(text="")

    try:
        from pdf2image import convert_from_path  # type: ignore
        import pytesseract  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.warning("ocr_deps_missing", error=str(e))
        return OCRResult(text="")

    try:
        images = convert_from_path(str(path), dpi=200)
    except Exception as e:  # noqa: BLE001
        log.warning("pdf2image_failed", path=str(path), error=str(e))
        return OCRResult(text="")

    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    confs: list[float] = []
    cursor = 0
    for img in images:
        text = pytesseract.image_to_string(img, lang=settings.ocr_langs)
        conf_data = pytesseract.image_to_data(
            img, lang=settings.ocr_langs, output_type=pytesseract.Output.DICT
        )
        raw_confs = [int(c) for c in conf_data.get("conf", []) if c not in ("-1", -1, "")]
        avg_conf = (sum(raw_confs) / len(raw_confs)) / 100 if raw_confs else 0.0
        parts.append(text)
        offsets.append((cursor, cursor + len(text)))
        confs.append(avg_conf)
        cursor += len(text) + 1
    return OCRResult(
        text="\n".join(parts),
        page_offsets=offsets,
        page_confidences=confs,
    )
