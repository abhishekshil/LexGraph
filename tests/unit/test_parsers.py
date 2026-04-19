from __future__ import annotations

from services.lib.parsers import parse_bytes


def test_text_parse_roundtrip():
    src = "Hello\nworld\n"
    pd = parse_bytes(src.encode("utf-8"), mime="text/plain", filename="x.txt")
    assert pd.text.strip() == "Hello\nworld"
    assert pd.page_offsets == [(0, len(pd.text))]


def test_html_parse_strips_boilerplate():
    html = (
        b"<html><head><title>t</title><style>x{}</style></head>"
        b"<body><nav>menu</nav>"
        b"<main><h1>Heading</h1><p>Body paragraph.</p></main>"
        b"<footer>copyright</footer></body></html>"
    )
    pd = parse_bytes(html, mime="text/html", filename="x.html")
    text = pd.text
    assert "Heading" in text and "Body paragraph." in text
    assert "menu" not in text
    assert "copyright" not in text


def test_unknown_bytes_falls_back_to_text():
    pd = parse_bytes(b"raw bytes here", mime="application/octet-stream", filename="x")
    assert "raw bytes" in pd.text
