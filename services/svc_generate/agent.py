"""GenerationAgent: evidence pack -> grounded Answer."""

from __future__ import annotations

from services.lib.bus.factory import Streams
from services.lib.data_models.events import (
    Event,
    QueryAnswerEvent,
    QueryEvidencePackEvent,
)
from services.lib.generation import GroundedGenerator
from services.agent_base import Agent


class GenerationAgent(Agent):
    name = "generation"
    listens = (Streams.QUERY_EVIDENCE_PACK,)
    publishes = (Streams.QUERY_ANSWER,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.gen = GroundedGenerator()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, QueryEvidencePackEvent):
            return
        answer = await self.gen.generate(event.pack, trace_id=event.trace_id)
        out = QueryAnswerEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            answer=answer,
        )
        await self.bus.publish(Streams.QUERY_ANSWER, out)
        self.log.info(
            "generation.done",
            confidence=answer.confidence,
            insufficient=answer.insufficient_evidence,
            citations=len(answer.legal_basis),
        )
