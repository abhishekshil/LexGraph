"""Dispatcher: RawDocument -> (text, per-page offsets).

Parsers accept either bytes (preferred) or a local path. Callers that have the
file in the object store should pass bytes — the dispatcher writes them to a
short-lived temp file only when the underlying library requires a real path
(e.g. pypdf's PdfReader).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..data_models.provenance import RawDocument


@dataclass
class ParsedDocument:
    text: str
    page_offsets: list[tuple[int, int]] = field(default_factory=list)
    mime: str = "text/plain"
    page_count: int = 1
    used_ocr: bool = False
    encrypted: bool = False   # set true if the source was PDF-encrypted


def parse_bytes(data: bytes, *, mime: str, filename: str = "") -> ParsedDocument:
    """Parse in-memory bytes into a :class:`ParsedDocument`."""
    suffix = Path(filename).suffix.lower() if filename else ""
    if mime == "application/pdf" or suffix == ".pdf":
        from .pdf_parser import parse_pdf_bytes

        return parse_pdf_bytes(data)
    if mime in (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ) or suffix == ".docx":
        from .docx_parser import parse_docx_bytes

        return parse_docx_bytes(data)
    if mime.startswith("text/html") or suffix in (".html", ".htm"):
        from .html_parser import parse_html_bytes

        return parse_html_bytes(data)

    from .text_parser import parse_text_bytes

    return parse_text_bytes(data)


def parse_raw_document(doc: RawDocument) -> ParsedDocument:
    """Parse a RawDocument that is *locally available* (file:// URI)."""
    uri = doc.file.storage_uri
    if uri.startswith("s3://"):
        raise RuntimeError(
            "parse_raw_document expects local bytes; callers must fetch via "
            "the object store first and use parse_bytes."
        )
    path = Path(uri.removeprefix("file://"))
    return parse_bytes(path.read_bytes(), mime=doc.file.mime, filename=path.name)


__all__ = ["ParsedDocument", "parse_bytes", "parse_raw_document", "_tempfile_for"]


def _tempfile_for(data: bytes, suffix: str) -> Path:
    """Write ``data`` to a NamedTemporaryFile and return its Path.

    Caller is responsible for unlinking when done.
    """
    f = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        f.write(data)
    finally:
        f.close()
    return Path(f.name)
