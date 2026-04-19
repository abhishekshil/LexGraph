"""PDF parser that preserves per-page offsets and flags encryption.

Strategy:
  1. Try pypdf on the in-memory bytes.
  2. If the document is encrypted and no password is available, mark the
     :class:`ParsedDocument` as ``encrypted`` and return empty text so the
     segment agent knows to skip OCR / downstream work cleanly.
  3. If a page yields < ``OCR_PAGE_THRESHOLD`` characters, the aggregate text
     will stay below ``MIN_TEXT_CHARS_BEFORE_OCR`` (in the segment agent) and
     the OCR path will run.
"""

from __future__ import annotations

import io

from ..core import get_logger
from .parser import ParsedDocument


log = get_logger("parser.pdf")


def parse_pdf_bytes(data: bytes) -> ParsedDocument:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.warning("pypdf_missing", error=str(e))
        return ParsedDocument(
            text="", page_offsets=[], mime="application/pdf", page_count=0
        )

    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as e:
        log.warning("pypdf.read_failed", error=str(e))
        return ParsedDocument(
            text="", page_offsets=[], mime="application/pdf", page_count=0
        )
    except Exception as e:  # noqa: BLE001
        log.warning("pypdf.read_failed", error=str(e))
        return ParsedDocument(
            text="", page_offsets=[], mime="application/pdf", page_count=0
        )

    encrypted = bool(getattr(reader, "is_encrypted", False))
    if encrypted:
        try:
            reader.decrypt("")
            encrypted = False
        except Exception:  # noqa: BLE001
            log.warning("pdf.encrypted")
            return ParsedDocument(
                text="",
                page_offsets=[],
                mime="application/pdf",
                page_count=len(reader.pages),
                encrypted=True,
            )

    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    for page in reader.pages:
        try:
            t = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001
            log.warning("pypdf.page_failed", error=str(e))
            t = ""
        parts.append(t)
        offsets.append((cursor, cursor + len(t)))
        cursor += len(t) + 1
    text = "\n".join(parts)
    return ParsedDocument(
        text=text,
        page_offsets=offsets,
        mime="application/pdf",
        page_count=len(reader.pages),
    )
