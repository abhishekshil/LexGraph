"""Event envelopes for the event bus.

Each agent subscribes to specific event types. Every event carries a trace_id
so we can follow a single query / ingestion across the whole agent graph.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from .answer import Answer
from .evidence import EvidencePack
from .metadata import DocumentMetadata
from .provenance import RawDocument, SourceEpisode, SourceSpan


class Event(BaseModel):
    """Envelope common to every bus message."""

    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex}")
    event_type: str
    trace_id: str
    tenant_id: str | None = None
    matter_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IngestRequestEvent(Event):
    event_type: Literal["ingest.request"] = "ingest.request"
    source: Literal["adapter", "upload"]
    adapter: str | None = None               # if source == "adapter"

    # For source == "upload": the API stores the file in MinIO first and then
    # publishes this event. All of these fields are populated by the API so the
    # IngestAgent can work without re-hashing (it can still verify on demand).
    upload_uri: str | None = None            # e.g. "s3://lexgraph-private/..."
    upload_bucket: str | None = None
    upload_key: str | None = None
    upload_filename: str | None = None
    upload_mime: str | None = None
    upload_sha256: str | None = None
    upload_size: int | None = None

    metadata: DocumentMetadata | None = None


class IngestCompletedEvent(Event):
    event_type: Literal["ingest.completed"] = "ingest.completed"
    raw_document: RawDocument
    episode: SourceEpisode


class SegmentCompletedEvent(Event):
    event_type: Literal["segment.completed"] = "segment.completed"
    episode_id: str
    spans: list[SourceSpan]
    hints: dict[str, Any] = Field(default_factory=dict)   # e.g. {"doctype": "statute_section"}


class EnrichCompletedEvent(Event):
    event_type: Literal["enrich.completed"] = "enrich.completed"
    episode_id: str
    # list of (node_type, props) tuples encoded as dicts
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class GraphWrittenEvent(Event):
    event_type: Literal["graph.written"] = "graph.written"
    episode_id: str
    node_ids: list[str]
    edge_count: int
    # Candidate points the semantic index layer should mirror. One entry per
    # successfully written node that is worth embedding. Populated by the
    # GraphWriterAgent so IndexAgent does not need to re-read the graph.
    indexable: list[dict[str, Any]] = Field(default_factory=list)


class IndexCompletedEvent(Event):
    event_type: Literal["index.completed"] = "index.completed"
    episode_id: str
    upserted: int
    collection_public: int = 0
    collection_private: int = 0
    skipped: int = 0
    embedder: str | None = None


class QueryRequestEvent(Event):
    event_type: Literal["query.request"] = "query.request"
    question: str
    matter_scope: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)   # jurisdiction, court, tier, date range, act
    mode: Literal["graph_only", "graph_plus_semantic", "graph_plus_semantic_plus_rerank"] = (
        "graph_plus_semantic"
    )


class QueryEvidencePackEvent(Event):
    event_type: Literal["query.evidence_pack"] = "query.evidence_pack"
    pack: EvidencePack


class QueryAnswerEvent(Event):
    event_type: Literal["query.answer"] = "query.answer"
    answer: Answer
