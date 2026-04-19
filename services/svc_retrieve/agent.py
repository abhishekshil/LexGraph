"""RetrievalAgent: builds an EvidencePack for every query.request event."""

from __future__ import annotations

from services.lib.bus.factory import Streams
from services.lib.data_models.events import (
    Event,
    QueryEvidencePackEvent,
    QueryRequestEvent,
)
from services.lib.retrieval import RetrievalOrchestrator
from services.agent_base import Agent


class RetrievalAgent(Agent):
    name = "retrieval"
    listens = (Streams.QUERY_REQUEST,)
    publishes = (Streams.QUERY_EVIDENCE_PACK,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.orch = RetrievalOrchestrator()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, QueryRequestEvent):
            return
        pack = await self.orch.answer(
            question=event.question,
            matter_scope=event.matter_scope,
            mode=event.mode,
        )
        out = QueryEvidencePackEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            pack=pack,
        )
        await self.bus.publish(Streams.QUERY_EVIDENCE_PACK, out)
        self.log.info("retrieval.pack_ready", insufficient=pack.insufficient_evidence,
                      spans=len(pack.spans))
