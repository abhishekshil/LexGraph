"""Redis Streams implementation of the EventBus."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import redis.asyncio as aioredis

from ..core import get_logger
from ..data_models.events import Event
from .base import EventBus, EventHandler


log = get_logger("bus.redis")


class RedisStreamsBus(EventBus):
    def __init__(self, url: str) -> None:
        self._r: aioredis.Redis = aioredis.from_url(url, decode_responses=True)

    async def publish(self, stream: str, event: Event) -> str:
        payload = {"data": event.model_dump_json()}
        msg_id = await self._r.xadd(stream, payload)
        log.debug("bus.publish", stream=stream, event_id=event.event_id, msg_id=msg_id)
        return msg_id  # type: ignore[return-value]

    async def _ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._r.xgroup_create(stream, group, id="$", mkstream=True)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise

    async def subscribe(
        self,
        stream: str,
        *,
        group: str,
        consumer: str,
        handler: EventHandler,
        block_ms: int = 5000,
    ) -> None:
        await self._ensure_group(stream, group)
        log.info("bus.subscribe", stream=stream, group=group, consumer=consumer)
        while True:
            resp = await self._r.xreadgroup(
                groupname=group,
                consumername=consumer,
                streams={stream: ">"},
                count=8,
                block=block_ms,
            )
            if not resp:
                continue
            for _stream_key, entries in resp:
                for msg_id, fields in entries:
                    try:
                        event = _deserialize(fields)
                        await handler(event)
                        await self._r.xack(stream, group, msg_id)
                    except Exception as e:  # noqa: BLE001
                        log.error(
                            "bus.handler_failed",
                            stream=stream,
                            msg_id=msg_id,
                            error=str(e),
                        )
                        # Do NOT ack; message becomes pending. After PEL
                        # threshold, a reaper may move it to DLQ.
                        await self.dead_letter(stream, _safe_event(fields), reason=str(e))
                        await self._r.xack(stream, group, msg_id)

    async def dead_letter(self, stream: str, event: Event, reason: str) -> None:
        dlq = f"{stream}.dlq"
        payload = {"data": event.model_dump_json(), "reason": reason}
        await self._r.xadd(dlq, payload)

    async def close(self) -> None:
        await self._r.close()


def _deserialize(fields: dict[str, Any]) -> Event:
    raw = fields.get("data")
    if not raw:
        raise ValueError("missing data field")
    obj = json.loads(raw)
    et = obj.get("event_type", "")
    # Local import to avoid circular imports at module init.
    from ..data_models.events import (
        EnrichCompletedEvent,
        GraphWrittenEvent,
        IngestCompletedEvent,
        IngestRequestEvent,
        QueryAnswerEvent,
        QueryEvidencePackEvent,
        QueryRequestEvent,
        SegmentCompletedEvent,
    )

    mapping: dict[str, type[Event]] = {
        "ingest.request": IngestRequestEvent,
        "ingest.completed": IngestCompletedEvent,
        "segment.completed": SegmentCompletedEvent,
        "enrich.completed": EnrichCompletedEvent,
        "graph.written": GraphWrittenEvent,
        "query.request": QueryRequestEvent,
        "query.evidence_pack": QueryEvidencePackEvent,
        "query.answer": QueryAnswerEvent,
    }
    cls = mapping.get(et, Event)
    return cls.model_validate(obj)


def _safe_event(fields: dict[str, Any]) -> Event:
    try:
        return _deserialize(fields)
    except Exception:
        return Event(event_type="unknown", trace_id="unknown")
