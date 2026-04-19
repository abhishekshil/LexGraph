"""Top-level segmenter dispatch.

Produces `LegalSegment`s (one per unit of legal structure) AND a node-shape
hint that the GraphWriterAgent uses to create typed nodes (Section / Paragraph
/ Exhibit / ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..data_models.metadata import DocumentKind


@dataclass
class LegalSegment:
    node_type: str                  # matches ontology.NodeType values
    label: str                      # e.g. "Section 378" or "Paragraph 12"
    text: str
    char_start: int
    char_end: int
    page: int | None = None
    parent_label: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SegmentResult:
    segments: list[LegalSegment]
    doctype_hint: DocumentKind


def segment_parsed_document(
    *,
    text: str,
    page_offsets: list[tuple[int, int]],
    doc_kind: DocumentKind,
) -> SegmentResult:
    from .judgment_segmenter import segment_judgment
    from .private_segmenter import segment_private
    from .statute_segmenter import segment_statute

    if doc_kind in {
        DocumentKind.STATUTE,
        DocumentKind.AMENDMENT_ACT,
        DocumentKind.RULE_SET,
        DocumentKind.REGULATION,
        DocumentKind.NOTIFICATION,
        DocumentKind.CIRCULAR,
    }:
        segs = segment_statute(text, page_offsets)
        return SegmentResult(segments=segs, doctype_hint=doc_kind)
    if doc_kind in {DocumentKind.JUDGMENT, DocumentKind.ORDER}:
        segs = segment_judgment(text, page_offsets)
        return SegmentResult(segments=segs, doctype_hint=doc_kind)
    segs = segment_private(text, page_offsets, doc_kind=doc_kind)
    return SegmentResult(segments=segs, doctype_hint=doc_kind)


def page_for_offset(offset: int, page_offsets: list[tuple[int, int]]) -> int | None:
    for idx, (s, e) in enumerate(page_offsets):
        if s <= offset < e:
            return idx + 1
    return None
