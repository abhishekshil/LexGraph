"""Provenance primitives.

These are the spine of the whole system: every extracted node must trace to a
SourceSpan, every SourceSpan must trace to a SourceEpisode, and every episode
must point at a File stored in object storage.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator


SourceKind = Literal["public", "private"]


class File(BaseModel):
    """Physical file in object storage (MinIO / S3)."""

    id: str = Field(default_factory=lambda: f"file_{uuid4().hex}")
    storage_uri: str  # e.g. "s3://lexgraph-private/matter_42/abc.pdf"
    mime: str
    sha256: str
    size: int
    filename: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("sha256")
    @classmethod
    def _sha_len(cls, v: str) -> str:
        if len(v) != 64:
            raise ValueError("sha256 must be 64 hex chars")
        return v


class SourceRef(BaseModel):
    """An adapter-emitted pointer to a source document to be fetched."""

    adapter: str                            # e.g. "india_code" / "sci_opendata"
    external_id: str                        # adapter-scoped id
    url: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class RawDocument(BaseModel):
    """Output of an ingestion adapter. Feeds the segmentation agent."""

    source_ref: SourceRef
    file: File
    kind: SourceKind
    # optional: prefetched metadata from the adapter; the enrichment layer may
    # refine or overwrite this later.
    metadata: dict[str, Any] = Field(default_factory=dict)
    matter_id: str | None = None            # set only for private ingestion


class SourceEpisode(BaseModel):
    """An ingestion event: 'this file was fetched/uploaded at this time'.

    Immutable. Retries create a NEW episode with a `supersedes` pointer so the
    audit trail is preserved.
    """

    id: str = Field(default_factory=lambda: f"ep_{uuid4().hex}")
    kind: SourceKind
    origin: str                             # adapter name or "upload"
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    file_id: str
    hash: str                               # sha256 of file bytes
    matter_id: str | None = None
    supersedes: str | None = None
    attribution: str | None = None          # license / source attribution text
    extra: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_file(
        cls,
        file: File,
        *,
        kind: SourceKind,
        origin: str,
        matter_id: str | None = None,
        attribution: str | None = None,
        supersedes: str | None = None,
    ) -> "SourceEpisode":
        return cls(
            kind=kind,
            origin=origin,
            file_id=file.id,
            hash=file.sha256,
            matter_id=matter_id,
            attribution=attribution,
            supersedes=supersedes,
        )


class SourceSpan(BaseModel):
    """Exact character range inside a file. Every citation must resolve to one."""

    id: str = Field(default_factory=lambda: f"span_{uuid4().hex}")
    episode_id: str
    file_id: str
    page: int | None = None                 # 1-indexed page number if available
    char_start: int
    char_end: int
    text: str
    ocr_confidence: float | None = None     # 0..1 when this span came from OCR
    matter_id: str | None = None            # propagated for retrieval scoping
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("char_end")
    @classmethod
    def _range(cls, v: int, info: Any) -> int:
        start = info.data.get("char_start")
        if start is not None and v < start:
            raise ValueError("char_end < char_start")
        return v


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
