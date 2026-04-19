"""Semantic fallback — activated when graph recall is thin.

Delegates to the shared :class:`QdrantIndexer` so public / private search use
the same embedding model and collection layout as the :class:`IndexAgent`
producer. Returns typed hits that the orchestrator joins back onto the graph
by ``node_id``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..core import get_logger, settings
from ..indexing import QdrantIndexer, get_indexer


log = get_logger("retrieval.semantic")


@dataclass
class SemanticHit:
    node_id: str
    score: float
    excerpt: str
    source_span_id: str | None = None
    authority_tier: int = 8
    title: str | None = None
    node_type: str | None = None
    section_ref: str | None = None
    case_ref: str | None = None
    matter_id: str | None = None


class SemanticFallback:
    """Thin async wrapper implementing the retrieval-layer contract."""

    def __init__(self, indexer: QdrantIndexer | None = None) -> None:
        self.indexer = indexer or get_indexer()

    async def recall(
        self,
        *,
        query: str,
        matter_scope: str | None = None,
        topk: int | None = None,
    ) -> list[SemanticHit]:
        topk = topk or settings.semantic_fallback_topk
        collection = self.indexer.collection_for(matter_id=matter_scope)
        try:
            hits = await self.indexer.search(
                collection=collection,
                query=query,
                topk=topk,
                matter_id=matter_scope,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("semantic.recall_failed", error=str(e))
            return []
        out: list[SemanticHit] = []
        for h in hits:
            payload = h.payload or {}
            out.append(
                SemanticHit(
                    node_id=h.node_id,
                    score=h.score,
                    excerpt=str(payload.get("text", ""))[:800],
                    source_span_id=payload.get("source_span_id"),
                    authority_tier=int(payload.get("authority_tier", 8)),
                    title=payload.get("title"),
                    node_type=payload.get("node_type"),
                    section_ref=payload.get("section_ref"),
                    case_ref=payload.get("case_ref"),
                    matter_id=payload.get("matter_id"),
                )
            )
        return out

    async def propose(
        self,
        question: str,
        *,
        matter_scope: str | None = None,
    ) -> list[str]:
        """Implements the :class:`SemanticSeedProvider` protocol."""
        hits = await self.recall(
            query=question,
            matter_scope=matter_scope,
            topk=settings.semantic_seed_topk,
        )
        return [h.node_id for h in hits]
