"""Evidence pack: the ONLY input the generator is allowed to see."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..ontology.authority import AuthorityTier


class EvidenceSpan(BaseModel):
    """A single excerpted source span with its provenance + authority."""

    marker: str                              # e.g. "S1", "S2" (used in prompt)
    node_id: str                             # graph node id that produced this span
    node_type: str                           # NodeType (as string)
    source_span_id: str
    source_episode_id: str
    file_id: str
    title: str | None = None                 # human title (case / act / doc)
    citation: str | None = None              # neutral / reported citation
    section_or_paragraph: str | None = None  # "S.378 IPC" / "para 12"
    court: str | None = None
    date: str | None = None                  # ISO-8601 string
    excerpt: str                             # the exact quoted text
    page: int | None = None
    char_start: int
    char_end: int
    tier: AuthorityTier
    score: float = 0.0                       # ranker score
    kind: Literal["public", "private"]
    matter_id: str | None = None


class EvidencePack(BaseModel):
    """Complete evidence context for a single query.

    The generation agent produces an Answer from this pack and NOTHING ELSE.
    """

    query: str
    query_type: str
    intent: dict[str, Any] = Field(default_factory=dict)
    spans: list[EvidenceSpan]
    graph_paths: list[list[str]] = Field(default_factory=list)     # each path: [node_id1, edge_type, node_id2, ...]
    summary_nodes: list[str] = Field(default_factory=list)         # ids of SummaryNode used
    conflicts: list[dict[str, Any]] = Field(default_factory=list)  # pairs of spans that disagree
    matter_scope: str | None = None
    confidence: Literal["low", "medium", "high"] = "medium"
    insufficient_evidence: bool = False
    retrieval_debug: dict[str, Any] = Field(default_factory=dict)
