"""Protocol for public-source ingestion adapters."""

from __future__ import annotations

from typing import AsyncIterator, Protocol, runtime_checkable

from ..data_models.provenance import RawDocument, SourceRef


@runtime_checkable
class PublicSourceAdapter(Protocol):
    """Every public-source adapter satisfies this shape."""

    name: str
    source_tier: int
    attribution: str   # license / credit text stamped on every SourceEpisode

    async def discover(self, **filters: object) -> AsyncIterator[SourceRef]: ...
    async def fetch(self, ref: SourceRef) -> RawDocument: ...
