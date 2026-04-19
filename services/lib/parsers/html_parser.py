"""HTML parser with boilerplate stripping.

Preserves only document body text and drops nav/script/style noise. We don't
pull a heavy readability dependency; the tag blacklist + common selectors
empirically cover statute viewers (indiacode.nic.in, ecourts, HC portals)
well.
"""

from __future__ import annotations

import re

from ..core import get_logger
from .parser import ParsedDocument


log = get_logger("parser.html")


_NOISE_TAGS = (
    "script", "style", "noscript", "nav", "header", "footer",
    "form", "iframe", "svg", "aside", "button",
)
_NOISE_SELECTORS = (
    "#sidebar", ".sidebar", ".nav", ".navbar", ".breadcrumb",
    ".header", ".footer", ".cookie", "#cookie", ".menu",
    ".social", ".share", ".advertisement",
)
_WS_RE = re.compile(r"[ \t\u00a0]+")
_NL_RE = re.compile(r"\n{3,}")


def parse_html_bytes(data: bytes) -> ParsedDocument:
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except Exception as e:  # noqa: BLE001
        log.warning("bs4_missing", error=str(e))
        # best-effort: strip tags with a regex
        raw = data.decode("utf-8", errors="replace")
        text = re.sub(r"<[^>]+>", " ", raw)
        text = _WS_RE.sub(" ", text).strip()
        return ParsedDocument(text=text, page_offsets=[(0, len(text))], mime="text/html")

    raw = data.decode("utf-8", errors="replace")
    try:
        soup = BeautifulSoup(raw, "lxml")
    except Exception:  # noqa: BLE001
        soup = BeautifulSoup(raw, "html.parser")

    for t in soup(list(_NOISE_TAGS)):
        t.decompose()
    for sel in _NOISE_SELECTORS:
        for t in soup.select(sel):
            t.decompose()

    # Prefer <main> or <article> when present.
    root = soup.find("main") or soup.find("article") or soup.body or soup
    text = root.get_text(separator="\n")
    text = _WS_RE.sub(" ", text)
    text = _NL_RE.sub("\n\n", text).strip()

    return ParsedDocument(
        text=text,
        page_offsets=[(0, len(text))],
        mime="text/html",
        page_count=1,
    )
