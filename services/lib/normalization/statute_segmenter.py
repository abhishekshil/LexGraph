"""Statute structure segmenter.

Detects Act→Part→Chapter→Section→Subsection→Proviso→Explanation→Illustration.
Deliberately regex-driven and conservative; handles typical Govt. of India
formatting variations.
"""

from __future__ import annotations

import re
from typing import Any

from .segment import LegalSegment, page_for_offset


# Act title detection. We look at the first ~40 lines of the document for
# "THE <ACT NAME>, <YEAR>" / "THE INDIAN PENAL CODE" / etc. The resulting act
# token is propagated onto every downstream Section segment so the enrichment
# pipeline can emit canonical node ids like ``section:ipc:378``.
_ACT_TITLE_RE = re.compile(
    r"\bTHE\s+([A-Z][A-Z&\-\s]{3,80}?(?:ACT|CODE|SANHITA|ADHINIYAM|CONSTITUTION))"
    r"(?:\s*,\s*(\d{4}))?",
    re.IGNORECASE,
)

# Common short forms → canonical act tokens used throughout the system.
_ACT_CANONICAL: dict[str, str] = {
    "indian penal code": "ipc",
    "ipc": "ipc",
    "bharatiya nyaya sanhita": "bns",
    "bns": "bns",
    "code of criminal procedure": "crpc",
    "crpc": "crpc",
    "bharatiya nagarik suraksha sanhita": "bnss",
    "bnss": "bnss",
    "indian evidence act": "iea",
    "iea": "iea",
    "bharatiya sakshya adhiniyam": "bsa",
    "bsa": "bsa",
    "constitution of india": "constitution",
    "constitution": "constitution",
}


def detect_act(text: str) -> tuple[str | None, str | None]:
    """Return ``(act_display_name, act_token)`` for the leading act, if any."""
    head = text[:4000]
    m = _ACT_TITLE_RE.search(head)
    if not m:
        return None, None
    name = re.sub(r"\s+", " ", m.group(1).strip().lower())
    # strip trailing generic word ("act" / "code") for canonical map lookup
    base = re.sub(r"\b(act|code|sanhita|adhiniyam|constitution)\b", "", name).strip()
    token = _ACT_CANONICAL.get(name) or _ACT_CANONICAL.get(base)
    if not token:
        token = re.sub(r"[^a-z0-9]+", "_", base or name).strip("_") or None
    display = m.group(1).strip() + (f", {m.group(2)}" if m.group(2) else "")
    return display, token


_PART_RE = re.compile(r"^\s*PART\s+([IVXLCDM]+)[\.\- ]?\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_CHAPTER_RE = re.compile(r"^\s*CHAPTER\s+([IVXLCDM]+|\d+)[\.\- ]?\s*(.*)$", re.MULTILINE | re.IGNORECASE)
_SECTION_RE = re.compile(
    r"""^\s*
        (?:Section\s+)?                     # optional 'Section' keyword
        (?P<num>\d+[A-Za-z]?)\.             # section number + a dot
        \s*(?P<heading>[^\n]{0,200})
    """,
    re.MULTILINE | re.VERBOSE,
)
_SUBSECTION_RE = re.compile(r"^\s*\((\d+[A-Za-z]?)\)\s", re.MULTILINE)
_PROVISO_RE = re.compile(r"^\s*Provided\s+(?:further\s+|also\s+)?that\b", re.MULTILINE | re.IGNORECASE)
_EXPLANATION_RE = re.compile(r"^\s*Explanation(?:\s+\d+)?\.\s*[—\-:]?", re.MULTILINE | re.IGNORECASE)
_ILLUSTRATION_RE = re.compile(r"^\s*Illustration(?:s)?\.", re.MULTILINE | re.IGNORECASE)


def segment_statute(text: str, page_offsets: list[tuple[int, int]]) -> list[LegalSegment]:
    out: list[LegalSegment] = []

    act_display, act_token = detect_act(text)
    if act_display and act_token:
        out.append(
            LegalSegment(
                node_type="Act",
                label=act_display,
                text=act_display,
                char_start=0,
                char_end=min(len(text), 2000),
                page=page_for_offset(0, page_offsets),
                extra={
                    "short_title": act_display,
                    "act_token": act_token,
                    "canonical_id": f"act:{act_token}",
                },
            )
        )

    current_part: str | None = None
    current_chapter: str | None = None
    current_section: LegalSegment | None = None

    # Collect anchor positions for every hierarchical marker.
    anchors: list[tuple[int, str, re.Match[str]]] = []
    for m in _PART_RE.finditer(text):
        anchors.append((m.start(), "Part", m))
    for m in _CHAPTER_RE.finditer(text):
        anchors.append((m.start(), "Chapter", m))
    for m in _SECTION_RE.finditer(text):
        anchors.append((m.start(), "Section", m))
    anchors.sort(key=lambda t: t[0])

    # Map section boundaries for slicing.
    section_ranges: list[tuple[int, int, re.Match[str]]] = []
    for i, (pos, kind, match) in enumerate(anchors):
        if kind != "Section":
            continue
        end = anchors[i + 1][0] if i + 1 < len(anchors) else len(text)
        section_ranges.append((pos, end, match))

    for pos, kind, match in anchors:
        if kind == "Part":
            current_part = match.group(1)
            out.append(
                LegalSegment(
                    node_type="Part",
                    label=f"Part {current_part}",
                    text=match.group(0).strip(),
                    char_start=match.start(),
                    char_end=match.end(),
                    page=page_for_offset(match.start(), page_offsets),
                    extra={"heading": (match.group(2) or "").strip()},
                )
            )
        elif kind == "Chapter":
            current_chapter = match.group(1)
            out.append(
                LegalSegment(
                    node_type="Chapter",
                    label=f"Chapter {current_chapter}",
                    text=match.group(0).strip(),
                    char_start=match.start(),
                    char_end=match.end(),
                    page=page_for_offset(match.start(), page_offsets),
                    parent_label=(f"Part {current_part}" if current_part else None),
                    extra={"heading": (match.group(2) or "").strip()},
                )
            )

    for start, end, match in section_ranges:
        section_text = text[start:end].rstrip()
        num = match.group("num")
        heading = (match.group("heading") or "").strip()
        section_label = f"Section {num}"
        section_extra: dict[str, Any] = {"number": num, "heading": heading}
        if act_token:
            section_extra["act_token"] = act_token
            section_extra["act_ref"] = act_display
            section_extra["canonical_id"] = f"section:{act_token}:{num.lower()}"
        sec_seg = LegalSegment(
            node_type="Section",
            label=section_label,
            text=section_text,
            char_start=start,
            char_end=end,
            page=page_for_offset(start, page_offsets),
            parent_label=(f"Chapter {current_chapter}" if current_chapter else None),
            extra=section_extra,
        )
        out.append(sec_seg)
        current_section = sec_seg

        # subsections
        for sm in _SUBSECTION_RE.finditer(section_text):
            sub_start = start + sm.start()
            # subsection runs until next subsection / explanation / proviso / illustration
            rest = section_text[sm.end():]
            local_end = _next_boundary(rest)
            sub_end = start + sm.end() + local_end if local_end is not None else end
            out.append(
                LegalSegment(
                    node_type="Subsection",
                    label=f"{section_label}({sm.group(1)})",
                    text=text[sub_start:sub_end].strip(),
                    char_start=sub_start,
                    char_end=sub_end,
                    page=page_for_offset(sub_start, page_offsets),
                    parent_label=section_label,
                    extra={"number": sm.group(1)},
                )
            )

        for pm in _PROVISO_RE.finditer(section_text):
            prov_start = start + pm.start()
            local_end = _next_boundary(section_text[pm.end():])
            prov_end = start + pm.end() + local_end if local_end is not None else end
            out.append(
                LegalSegment(
                    node_type="Proviso",
                    label=f"{section_label} - proviso",
                    text=text[prov_start:prov_end].strip(),
                    char_start=prov_start,
                    char_end=prov_end,
                    page=page_for_offset(prov_start, page_offsets),
                    parent_label=section_label,
                )
            )

        for em in _EXPLANATION_RE.finditer(section_text):
            ex_start = start + em.start()
            local_end = _next_boundary(section_text[em.end():])
            ex_end = start + em.end() + local_end if local_end is not None else end
            out.append(
                LegalSegment(
                    node_type="Explanation",
                    label=f"{section_label} - explanation",
                    text=text[ex_start:ex_end].strip(),
                    char_start=ex_start,
                    char_end=ex_end,
                    page=page_for_offset(ex_start, page_offsets),
                    parent_label=section_label,
                )
            )

        for im in _ILLUSTRATION_RE.finditer(section_text):
            il_start = start + im.start()
            local_end = _next_boundary(section_text[im.end():])
            il_end = start + im.end() + local_end if local_end is not None else end
            out.append(
                LegalSegment(
                    node_type="Illustration",
                    label=f"{section_label} - illustration",
                    text=text[il_start:il_end].strip(),
                    char_start=il_start,
                    char_end=il_end,
                    page=page_for_offset(il_start, page_offsets),
                    parent_label=section_label,
                )
            )

    return out


_BOUNDARY = re.compile(
    r"(?:^\s*\(\d+[A-Za-z]?\)\s)|(?:^\s*Provided\b)|(?:^\s*Explanation(?:\s+\d+)?\.)|(?:^\s*Illustration)",
    re.MULTILINE | re.IGNORECASE,
)


def _next_boundary(after: str) -> int | None:
    m = _BOUNDARY.search(after)
    return m.start() if m else None
