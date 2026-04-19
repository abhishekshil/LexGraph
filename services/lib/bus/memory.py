"""In-memory event bus. Use for tests / single-process development.

Not suitable for production (no durability, no cross-process). Implements the
same contract as the Redis Streams bus so agents behave identically.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from ..core import get_logger
from ..data_models.events import Event
from .base import EventBus, EventHandler


log = get_logger("bus.memory")


class InMemoryBus(EventBus):
    def __init__(self) -> None:
        self._queues: dict[str, asyncio.Queue[Event]] = defaultdict(asyncio.Queue)
        self._dlq: list[tuple[str, Event, str]] = []
        self._published: list[tuple[str, Event]] = []
        self._closed = False

    async def publish(self, stream: str, event: Event) -> str:
        if self._closed:
            raise RuntimeError("bus closed")
        await self._queues[stream].put(event)
        self._published.append((stream, event))
        return f"mem_{len(self._published)}"

    async def subscribe(
        self,
        stream: str,
        *,
        group: str,
        consumer: str,
        handler: EventHandler,
        block_ms: int = 5000,
    ) -> None:
        q = self._queues[stream]
        while not self._closed:
            try:
                evt = await asyncio.wait_for(q.get(), timeout=block_ms / 1000)
            except asyncio.TimeoutError:
                continue
            try:
                await handler(evt)
            except Exception as e:  # noqa: BLE001
                log.warning("memory.handler_failed", stream=stream, error=str(e))
                await self.dead_letter(stream, evt, str(e))

    async def dead_letter(self, stream: str, event: Event, reason: str) -> None:
        self._dlq.append((stream, event, reason))
        log.warning("memory.dlq", stream=stream, reason=reason)

    async def close(self) -> None:
        self._closed = True

    # -- test helpers -------------------------------------------------------

    async def drain(
        self,
        stream: str,
        handler: EventHandler,
        *,
        expected: int | None = None,
        timeout_s: float = 5.0,
    ) -> int:
        """Process all pending events on ``stream``. Returns how many ran.

        If ``expected`` is provided, waits until exactly that many have arrived
        (or the timeout elapses). If the handler publishes to ``stream``, those
        are drained too — consumers should stop themselves via ``expected``.
        """
        q = self._queues[stream]
        processed = 0
        deadline = asyncio.get_event_loop().time() + timeout_s
        while processed < (expected or 1_000_000):
            remaining = deadline - asyncio.get_event_loop().time()
            if remaining <= 0:
                break
            try:
                evt = await asyncio.wait_for(q.get(), timeout=min(remaining, 1.0))
            except asyncio.TimeoutError:
                if expected is None:
                    break
                continue
            await handler(evt)
            processed += 1
            if expected is None and q.empty():
                break
        return processed

    def published_on(self, stream: str) -> list[Event]:
        return [e for (s, e) in self._published if s == stream]

    @property
    def dlq(self) -> list[tuple[str, Event, str]]:
        return list(self._dlq)
