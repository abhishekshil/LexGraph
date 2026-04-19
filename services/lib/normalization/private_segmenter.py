"""Private-document segmenter.

Private case materials don't follow statutory structure. Heuristics here:

  * FIR: pick up the offence-sections column, victim/accused header lines, and
    the narrative block.
  * Chargesheet: pick up the accused table, witness list (PW/DW), and the
    offence sections.
  * Contracts: pick up numbered clauses, definitions, and schedules.
  * Witness statements / affidavits: pick up "Statement of X, aged Y".
  * Exhibits: Ex. P-1 / Ex. D-2 / Annexure A.
  * Correspondence & emails: page-level block.

Each resulting segment becomes a ``Document`` / ``Exhibit`` / ``Statement`` /
``ContractClause`` / ``Notice`` / ``Communication`` node. Extras include
extracted entities that the enrichment agent can promote into graph nodes.
"""

from __future__ import annotations

import re

from ..data_models.metadata import DocumentKind
from .segment import LegalSegment


_EXHIBIT_RE = re.compile(
    r"\b(Ex(?:hibit)?\.?\s*[PDC]?-?\s*\d+[A-Za-z]?)\b", re.IGNORECASE
)
_ANNEX_RE = re.compile(r"\b(Annex(?:ure)?\s+[A-Z0-9]+)\b", re.IGNORECASE)
_WITNESS_RE = re.compile(
    r"\b(?:Statement|Deposition|Cross[-\s]?examination|Examination[-\s]?in[-\s]?chief)\s+of\s+([A-Z][A-Za-z\.\- ]+)\b"
)
_PW_DW_RE = re.compile(r"\b(P\.?W\.?|D\.?W\.?|C\.?W\.?)\s*[-:\s]*(\d+)\b")

_CLAUSE_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+)*)\.\s+(?=[A-Z])",
    re.MULTILINE,
)
_DEF_RE = re.compile(r"^\s*\"([^\"]+)\"\s+(?:means|shall mean)\b", re.MULTILINE)
_SCHEDULE_RE = re.compile(r"^\s*SCHEDULE\s+[A-Z0-9]+\b", re.MULTILINE | re.IGNORECASE)

# FIR / chargesheet specific
_FIR_HEADER_RE = re.compile(
    r"(?:FIR\s*No\.?|First\s+Information\s+Report\s+No\.?)\s*[:.]?\s*(\S+)",
    re.IGNORECASE,
)
_FIR_SECTIONS_RE = re.compile(
    r"(?:Sections?|u/s|under\s+section[s]?)\s*[:.]?\s*([\dA-Za-z,\s\(\)/&]+?)(?=\b(?:of|IPC|CrPC|BNS|BNSS|BSA)\b)",
    re.IGNORECASE,
)
_CHARGESHEET_HEADER_RE = re.compile(
    r"(?:Charge[-\s]?sheet|Final\s+Report|Final\s+Form)\s*(?:No\.?)?\s*[:.]?", re.IGNORECASE
)
_ACCUSED_ROW_RE = re.compile(
    r"\bAccused\b\s*(?:No\.?)?\s*(\d+)?\s*[:.\-]?\s*([A-Z][A-Za-z\.\- ]{2,})",
)

_BLOCK_RE = re.compile(r"\n\s*\n")


def segment_private(
    text: str,
    page_offsets: list[tuple[int, int]],
    *,
    doc_kind: DocumentKind,
) -> list[LegalSegment]:
    if not page_offsets:
        page_offsets = [(0, len(text))]

    # Document-kind specialised paths.
    if doc_kind == DocumentKind.CONTRACT:
        return _segment_contract(text, page_offsets)
    if doc_kind == DocumentKind.FIR:
        return _segment_fir(text, page_offsets)
    if doc_kind == DocumentKind.CHARGESHEET:
        return _segment_chargesheet(text, page_offsets)

    return _segment_generic_blocks(text, page_offsets, doc_kind)


# --- generic (blocks) ------------------------------------------------------


def _segment_generic_blocks(
    text: str,
    page_offsets: list[tuple[int, int]],
    doc_kind: DocumentKind,
) -> list[LegalSegment]:
    out: list[LegalSegment] = []
    for page_idx, (page_start, page_end) in enumerate(page_offsets, start=1):
        page_text = text[page_start:page_end]
        offset = page_start
        for block in _BLOCK_RE.split(page_text):
            stripped = block.strip()
            if not stripped:
                offset += len(block) + 2
                continue
            b_start = text.find(stripped, offset)
            if b_start < 0:
                b_start = offset
            b_end = b_start + len(stripped)
            out.append(
                LegalSegment(
                    node_type=_node_type_for_block(stripped, doc_kind),
                    label=_label_for_block(stripped, doc_kind, page_idx),
                    text=stripped,
                    char_start=b_start,
                    char_end=b_end,
                    page=page_idx,
                    extra=_extras_for_block(stripped, doc_kind),
                )
            )
            offset = b_end
    return out


# --- contracts ------------------------------------------------------------


def _segment_contract(
    text: str, page_offsets: list[tuple[int, int]]
) -> list[LegalSegment]:
    out: list[LegalSegment] = []

    # Definitions block
    for m in _DEF_RE.finditer(text):
        defn_end = text.find("\n\n", m.start())
        if defn_end < 0:
            defn_end = min(len(text), m.start() + 400)
        out.append(
            LegalSegment(
                node_type="ContractClause",
                label=f"Definition: {m.group(1)}",
                text=text[m.start():defn_end].strip(),
                char_start=m.start(),
                char_end=defn_end,
                extra={"role": "definition", "term": m.group(1)},
            )
        )

    # Numbered clauses
    matches = list(_CLAUSE_RE.finditer(text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out.append(
            LegalSegment(
                node_type="ContractClause",
                label=f"Clause {m.group('num')}",
                text=text[start:end].strip(),
                char_start=start,
                char_end=end,
                extra={"number": m.group("num")},
            )
        )

    # Schedules
    for m in _SCHEDULE_RE.finditer(text):
        end = text.find("\n\n", m.end())
        if end < 0:
            end = min(len(text), m.start() + 2000)
        out.append(
            LegalSegment(
                node_type="Document",
                label=text[m.start(): m.end()].strip(),
                text=text[m.start():end].strip(),
                char_start=m.start(),
                char_end=end,
                extra={"role": "schedule"},
            )
        )

    # Fallback: if we found nothing structural, emit a single block so
    # downstream agents still see provenance.
    if not out and text.strip():
        out.append(
            LegalSegment(
                node_type="ContractClause",
                label="Contract (unstructured)",
                text=text.strip(),
                char_start=0,
                char_end=len(text),
            )
        )
    return out


# --- FIRs ------------------------------------------------------------------


def _segment_fir(text: str, page_offsets: list[tuple[int, int]]) -> list[LegalSegment]:
    out: list[LegalSegment] = []

    header = _FIR_HEADER_RE.search(text)
    sections = _FIR_SECTIONS_RE.search(text)
    extras: dict[str, object] = {"doc_kind": "fir"}
    if header:
        extras["fir_number"] = header.group(1)
    if sections:
        extras["offence_sections"] = sections.group(1).strip()

    out.append(
        LegalSegment(
            node_type="Document",
            label="FIR Header",
            text=text[: min(len(text), 1600)].strip(),
            char_start=0,
            char_end=min(len(text), 1600),
            extra=extras,
        )
    )

    # Narrative body (rest of doc) as a single block; enrichment will carve it.
    if len(text) > 1600:
        out.append(
            LegalSegment(
                node_type="Document",
                label="FIR Narrative",
                text=text[1600:].strip(),
                char_start=1600,
                char_end=len(text),
                extra={"doc_kind": "fir", "role": "narrative"},
            )
        )
    return out


# --- chargesheets ----------------------------------------------------------


def _segment_chargesheet(
    text: str, page_offsets: list[tuple[int, int]]
) -> list[LegalSegment]:
    out: list[LegalSegment] = []

    # Header block
    header_end = min(len(text), 1200)
    if _CHARGESHEET_HEADER_RE.search(text[:header_end]):
        extras: dict[str, object] = {"doc_kind": "chargesheet"}
        sections = _FIR_SECTIONS_RE.search(text[:header_end])
        if sections:
            extras["offence_sections"] = sections.group(1).strip()
        out.append(
            LegalSegment(
                node_type="Document",
                label="Chargesheet Header",
                text=text[:header_end].strip(),
                char_start=0,
                char_end=header_end,
                extra=extras,
            )
        )

    # Accused rows (one segment per accused)
    for m in _ACCUSED_ROW_RE.finditer(text):
        end = min(len(text), m.end() + 160)
        out.append(
            LegalSegment(
                node_type="Party",
                label=f"Accused {m.group(1) or ''}".strip(),
                text=text[m.start():end].strip(),
                char_start=m.start(),
                char_end=end,
                extra={"party_role": "accused", "name": m.group(2).strip()},
            )
        )

    # Witness list (PW/DW/CW)
    for m in _PW_DW_RE.finditer(text):
        end = min(len(text), m.end() + 120)
        out.append(
            LegalSegment(
                node_type="Witness",
                label=f"{m.group(1).replace('.', '').upper()}{m.group(2)}",
                text=text[m.start():end].strip(),
                char_start=m.start(),
                char_end=end,
                extra={"witness_type": m.group(1).replace(".", "").upper()},
            )
        )

    # Narrative body as a fallback block so tests always see at least one
    # segment.
    if not out and text.strip():
        out.append(
            LegalSegment(
                node_type="Document",
                label="Chargesheet (unstructured)",
                text=text.strip(),
                char_start=0,
                char_end=len(text),
                extra={"doc_kind": "chargesheet"},
            )
        )
    return out


# --- generic helpers -------------------------------------------------------


def _node_type_for_block(block: str, doc_kind: DocumentKind) -> str:
    if _EXHIBIT_RE.search(block) or _ANNEX_RE.search(block):
        return "Exhibit"
    if _WITNESS_RE.search(block) or doc_kind == DocumentKind.WITNESS_STATEMENT:
        return "Statement"
    if doc_kind == DocumentKind.NOTICE:
        return "Notice"
    if doc_kind in {DocumentKind.EMAIL, DocumentKind.CORRESPONDENCE}:
        return "Communication"
    return "Document"


def _label_for_block(block: str, doc_kind: DocumentKind, page_idx: int) -> str:
    ex = _EXHIBIT_RE.search(block)
    if ex:
        return ex.group(1)
    an = _ANNEX_RE.search(block)
    if an:
        return an.group(1)
    wn = _WITNESS_RE.search(block)
    if wn:
        return f"Statement of {wn.group(1).strip()}"
    return f"{doc_kind.value} p.{page_idx}"


def _extras_for_block(block: str, doc_kind: DocumentKind) -> dict[str, object]:
    extras: dict[str, object] = {"doc_kind": doc_kind.value}
    wn = _WITNESS_RE.search(block)
    if wn:
        extras["witness_name"] = wn.group(1).strip()
    ex = _EXHIBIT_RE.search(block)
    if ex:
        extras["exhibit_label"] = ex.group(1)
    return extras
