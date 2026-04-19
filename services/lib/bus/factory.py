from __future__ import annotations

from functools import lru_cache

from ..core import settings
from .base import EventBus
from .redis_streams import RedisStreamsBus


# Canonical stream names used across agents.
class Streams:
    INGEST_REQUEST = "ingest.request"
    INGEST_COMPLETED = "ingest.completed"
    SEGMENT_COMPLETED = "segment.completed"
    ENRICH_COMPLETED = "enrich.completed"
    GRAPH_WRITTEN = "graph.written"
    INDEX_COMPLETED = "index.completed"
    QUERY_REQUEST = "query.request"
    QUERY_EVIDENCE_PACK = "query.evidence_pack"
    QUERY_ANSWER = "query.answer"
    EVAL_REQUEST = "eval.request"
    EVAL_REPORT = "eval.report"


@lru_cache
def get_bus() -> EventBus:
    backend = settings.event_bus_backend
    if backend == "redis-streams":
        return RedisStreamsBus(settings.redis_url)
    if backend in {"memory", "in-memory", "inmemory"}:
        from .memory import InMemoryBus

        return InMemoryBus()
    raise NotImplementedError(f"event bus backend: {backend}")


def reset_bus_for_tests() -> None:
    """Clear the cached bus so tests can swap backends via settings."""
    get_bus.cache_clear()
