"""IndexAgent: mirrors graph nodes into the Qdrant semantic index.

Listens on ``graph.written``. For every indexable payload produced by the
GraphWriterAgent, builds an :class:`IndexPayload` and upserts into the
appropriate collection (public vs. matter-scoped private). Publishes
``index.completed`` so downstream components (eval / observability) can follow
the pipeline end-to-end.

Idempotent by design: the Qdrant point id is derived from the graph ``node_id``
so re-writes simply update in place. A no-op path is used when the embedder /
Qdrant are unavailable, which keeps ingestion robust in development.
"""

from __future__ import annotations

from typing import Any

from services.lib.bus.factory import Streams
from services.lib.data_models.events import (
    Event,
    GraphWrittenEvent,
    IndexCompletedEvent,
)
from services.lib.indexing import IndexPayload, get_indexer
from services.agent_base import Agent


class IndexAgent(Agent):
    name = "index"
    listens = (Streams.GRAPH_WRITTEN,)
    publishes = (Streams.INDEX_COMPLETED,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.indexer = get_indexer()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, GraphWrittenEvent):
            return
        if not event.indexable:
            await self._publish(event, public=0, private=0, skipped=0)
            return

        public_payloads: list[IndexPayload] = []
        private_payloads: dict[str, list[IndexPayload]] = {}
        skipped = 0

        for raw in event.indexable:
            payload = _payload_from_raw(raw)
            if payload is None or not payload.text.strip():
                skipped += 1
                continue
            if payload.matter_id:
                private_payloads.setdefault(payload.matter_id, []).append(payload)
            else:
                public_payloads.append(payload)

        public_written = 0
        private_written = 0

        if public_payloads:
            public_written = await self.indexer.upsert(
                collection=self.indexer.collection_for(matter_id=None),
                payloads=public_payloads,
            )

        for matter_id, points in private_payloads.items():
            # All private points share one logical collection; isolation is
            # enforced by the ``matter_id`` filter on search.
            private_written += await self.indexer.upsert(
                collection=self.indexer.collection_for(matter_id=matter_id),
                payloads=points,
            )

        await self._publish(event, public=public_written, private=private_written, skipped=skipped)
        self.log.info(
            "index.completed",
            episode_id=event.episode_id,
            public=public_written,
            private=private_written,
            skipped=skipped,
        )

    async def _publish(
        self,
        event: GraphWrittenEvent,
        *,
        public: int,
        private: int,
        skipped: int,
    ) -> None:
        out = IndexCompletedEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            episode_id=event.episode_id,
            upserted=public + private,
            collection_public=public,
            collection_private=private,
            skipped=skipped,
            embedder=self.indexer._embedder.model_name,
        )
        await self.bus.publish(Streams.INDEX_COMPLETED, out)


def _payload_from_raw(raw: dict[str, Any]) -> IndexPayload | None:
    node_id = raw.get("node_id")
    node_type = raw.get("node_type")
    text = raw.get("text")
    tier = raw.get("authority_tier")
    if not node_id or not node_type or text is None or tier is None:
        return None
    return IndexPayload(
        node_id=str(node_id),
        node_type=str(node_type),
        text=str(text),
        authority_tier=int(tier),
        matter_id=raw.get("matter_id"),
        source_span_id=raw.get("source_span_id"),
        file_id=raw.get("file_id"),
        episode_id=raw.get("episode_id"),
        section_ref=raw.get("section_ref"),
        case_ref=raw.get("case_ref"),
        title=raw.get("title"),
        citation=raw.get("citation"),
        court=raw.get("court"),
        date=raw.get("date"),
    )
