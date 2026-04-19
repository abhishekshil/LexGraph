"""Canonical Qdrant payload schema.

Every point we store in Qdrant has this exact payload. Keeping it typed makes
the semantic-fallback retriever trivially reliable: it just reads well-known
keys and joins them back to graph nodes by ``node_id``.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from ..ontology import NodeType


# Only index nodes that carry prose worth embedding. Structural containers
# (Act, Chapter) have no meaningful text by themselves; they are reachable via
# BFS from their children anyway.
INDEXABLE_NODE_TYPES: frozenset[NodeType] = frozenset(
    {
        NodeType.SECTION,
        NodeType.SUBSECTION,
        NodeType.PROVISO,
        NodeType.EXPLANATION,
        NodeType.ILLUSTRATION,
        NodeType.PARAGRAPH,
        NodeType.HOLDING,
        NodeType.RATIO,
        NodeType.OBITER,
        NodeType.ISSUE,
        NodeType.LEGAL_TEST,
        NodeType.DOCTRINE,
        NodeType.OFFENCE,
        NodeType.INGREDIENT,
        NodeType.PUNISHMENT,
        NodeType.PROCEDURE,
        NodeType.EVIDENCE_RULE,
        NodeType.STATEMENT,
        NodeType.FACT,
        NodeType.ALLEGATION,
        NodeType.DEFENSE,
        NodeType.CONTRADICTION,
        NodeType.CONTRACT_CLAUSE,
        NodeType.ARGUMENT,
        NodeType.EXHIBIT,
        NodeType.SUMMARY_NODE,
    }
)


@dataclass
class IndexPayload:
    """Typed payload for a single Qdrant point."""

    node_id: str
    node_type: str
    text: str
    authority_tier: int
    matter_id: str | None = None
    source_span_id: str | None = None
    file_id: str | None = None
    episode_id: str | None = None
    section_ref: str | None = None            # "section:bns:303"
    case_ref: str | None = None               # "case:<id>"
    title: str | None = None
    citation: str | None = None
    court: str | None = None
    date: str | None = None                   # ISO
    language: str = "en"
    extras: dict[str, Any] = field(default_factory=dict)


def payload_to_dict(p: IndexPayload) -> dict[str, Any]:
    """Flatten to a Qdrant-compatible payload dict (no None values)."""
    raw = asdict(p)
    flat: dict[str, Any] = {}
    for k, v in raw.items():
        if v is None:
            continue
        if k == "extras" and isinstance(v, dict):
            # promote extras under a stable prefix so they are filterable too
            for ek, ev in v.items():
                if ev is None:
                    continue
                flat[f"ex.{ek}"] = ev
            continue
        flat[k] = v
    return flat
