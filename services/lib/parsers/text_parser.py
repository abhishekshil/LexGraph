from __future__ import annotations

from .parser import ParsedDocument


def parse_text_bytes(data: bytes) -> ParsedDocument:
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = data.decode("utf-8", errors="replace")
    return ParsedDocument(
        text=text,
        page_offsets=[(0, len(text))],
        mime="text/plain",
        page_count=1,
    )
