"""Answer schema - the machine-readable + human-readable shape of every reply."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..ontology.authority import AuthorityTier


class AnswerCitation(BaseModel):
    """One cited source, resolved from an [S#] marker in the generated text."""

    marker: str
    type: Literal["statute", "judgment", "rule", "regulation",
                  "notification", "private_document", "private_note", "summary"]
    title: str | None = None
    authority: str | None = None             # e.g. "Supreme Court of India"
    court: str | None = None
    date: str | None = None
    section_or_paragraph: str | None = None
    excerpt: str
    source_id: str                           # SourceEpisode id
    source_span_id: str
    file_id: str
    chunk_id: str | None = None
    node_id: str
    tier: AuthorityTier
    score: float = 0.0


class AnswerConflict(BaseModel):
    description: str
    citations: list[str]                     # marker ids (S1, S2, ...)
    severity: Literal["low", "medium", "high"] = "medium"


class GraphPath(BaseModel):
    """Human-readable path explaining how the system reached an authority."""

    nodes: list[str]                         # ids in order
    edges: list[str]                         # edge types in order
    narrative: str                           # one-sentence path explanation


class Answer(BaseModel):
    """Final, grounded answer. This is the API response shape."""

    question: str
    query_type: str
    answer: str                              # the human-readable answer (with [S#] markers kept)
    legal_basis: list[AnswerCitation] = Field(default_factory=list)
    supporting_private_sources: list[AnswerCitation] = Field(default_factory=list)
    graph_paths: list[GraphPath] = Field(default_factory=list)
    conflicts: list[AnswerConflict] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
    insufficient_evidence: bool = False
    notes: list[str] = Field(default_factory=list)
    trace_id: str
    evidence_pack_id: str | None = None
    extras: dict[str, Any] = Field(default_factory=dict)
