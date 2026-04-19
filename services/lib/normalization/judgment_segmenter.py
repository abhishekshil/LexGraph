"""Judgment segmenter.

Produces Paragraph segments keyed by paragraph numbers with rhetorical-role
hints attached. Covers the headings commonly found in Indian judgments:

  - "FACTS OF THE CASE" / "BACKGROUND" / "PROSECUTION CASE"            → facts
  - "ISSUES FOR CONSIDERATION" / "POINTS FOR DETERMINATION"            → issues
  - "SUBMISSIONS" / "CONTENTIONS" / "ARGUMENTS"                         → arguments
  - "ANALYSIS" / "DISCUSSION" / "REASONING" / "OUR VIEW"                → analysis
  - "RATIO DECIDENDI"                                                   → ratio
  - "OBITER" / "IN PASSING"                                             → obiter
  - "HELD" / "CONCLUSION"                                               → holding
  - "ORDER" / "DISPOSAL" / "IN FINE" / "APPEAL IS DISMISSED"            → order
  - "INGREDIENT(S)" of / elements of offence phrasing                   → ingredients

Also applies simple heuristics to detect disposal verbs at the tail of the
judgment and tag them so the retrieval layer can prefer them.
"""

from __future__ import annotations

import re

from .segment import LegalSegment, page_for_offset


_PARA_RE = re.compile(
    r"^\s*(?P<num>\d+)\.\s+(?=[A-Z\"\u2018\u201c])",  # "12. The..." at line start
    re.MULTILINE,
)

_RHETORICAL_HINTS: dict[str, str] = {
    r"\bFACTS?\s+OF\s+THE\s+CASE\b": "facts",
    r"\bBACKGROUND\b": "facts",
    r"\bPROSECUTION\s+CASE\b": "facts",
    r"\bFACTUAL\s+MATRIX\b": "facts",
    r"\bISSUES?\s+FOR\s+(?:CONSIDERATION|DETERMINATION)\b": "issues",
    r"\bPOINTS?\s+FOR\s+DETERMINATION\b": "issues",
    r"\bQUESTION(?:S)?\s+OF\s+LAW\b": "issues",
    r"\bCONTENTION[S]?\b": "arguments",
    r"\bSUBMISSION[S]?\b": "arguments",
    r"\bARGUED\s+THAT\b": "arguments",
    r"\bANALYSIS\b": "analysis",
    r"\bDISCUSSION\b": "analysis",
    r"\bREASONING\b": "analysis",
    r"\bOUR\s+VIEW\b": "analysis",
    r"\bRATIO\s+DECIDENDI\b": "ratio",
    r"\bOBITER\s+DICTA?\b": "obiter",
    r"\bIN\s+PASSING\b": "obiter",
    r"\bHELD\b": "holding",
    r"\bWE\s+HOLD\b": "holding",
    r"\bINGREDIENTS?\s+OF\b": "ingredients",
    r"\bESSENTIAL\s+ELEMENTS?\b": "ingredients",
    r"\bORDER\b": "order",
    r"\bDISPOSAL\b": "order",
    r"\bIN\s+(?:FINE|THE\s+RESULT)\b": "order",
    r"\bAPPEAL\s+IS\s+(?:DISMISSED|ALLOWED|PARTLY\s+ALLOWED)\b": "order",
    r"\bPETITION\s+IS\s+(?:DISMISSED|ALLOWED|PARTLY\s+ALLOWED)\b": "order",
    r"\bCONVICTION\s+IS\s+(?:SET\s+ASIDE|UPHELD|CONFIRMED)\b": "order",
}

_DISPOSAL_VERB_RE = re.compile(
    r"\b(?:allowed|dismissed|set\s+aside|remanded|quashed|confirmed|upheld|acquitted|convicted)\b",
    re.IGNORECASE,
)


def segment_judgment(text: str, page_offsets: list[tuple[int, int]]) -> list[LegalSegment]:
    out: list[LegalSegment] = []

    matches = list(_PARA_RE.finditer(text))
    if not matches:
        # Fallback: single-paragraph judgment (short order / summary)
        if text.strip():
            out.append(
                LegalSegment(
                    node_type="Paragraph",
                    label="Paragraph 1",
                    text=text.strip(),
                    char_start=0,
                    char_end=len(text),
                    page=1 if page_offsets else None,
                    extra={"number": "1"},
                )
            )
        return _attach_roles(text, out)

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append(
            LegalSegment(
                node_type="Paragraph",
                label=f"Paragraph {m.group('num')}",
                text=text[start:end].strip(),
                char_start=start,
                char_end=end,
                page=page_for_offset(start, page_offsets),
                extra={"number": m.group("num")},
            )
        )

    return _attach_roles(text, out)


def _attach_roles(text: str, segs: list[LegalSegment]) -> list[LegalSegment]:
    for pat, role in _RHETORICAL_HINTS.items():
        for m in re.finditer(pat, text, flags=re.IGNORECASE):
            for seg in segs:
                if seg.char_start <= m.start() <= seg.char_end:
                    roles = seg.extra.setdefault("rhetorical_roles", [])
                    if role not in roles:
                        roles.append(role)
                    break

    # Tail-paragraph disposal heuristic.
    if segs:
        last = segs[-1]
        if _DISPOSAL_VERB_RE.search(last.text):
            roles = last.extra.setdefault("rhetorical_roles", [])
            if "order" not in roles:
                roles.append("order")

    return segs
