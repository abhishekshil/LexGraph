"""Common plumbing for every agent (lives under ``services/`` with implementations)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from services.lib.bus import EventBus, get_bus
from services.lib.core import get_logger
from services.lib.data_models.events import Event


class Agent(ABC):
    name: ClassVar[str] = "agent"
    listens: ClassVar[tuple[str, ...]] = ()
    publishes: ClassVar[tuple[str, ...]] = ()

    def __init__(self, bus: EventBus | None = None) -> None:
        self.bus = bus or get_bus()
        self.log = get_logger(f"agent.{self.name}")

    async def run_forever(self, *, consumer: str | None = None) -> None:
        """Subscribe to every listen stream and dispatch to self.handle."""
        import asyncio

        consumer = consumer or f"{self.name}-1"

        async def _sub(stream: str) -> None:
            await self.bus.subscribe(
                stream,
                group=self.name,
                consumer=consumer,  # type: ignore[arg-type]
                handler=self._safe_handle,
            )

        tasks = [asyncio.create_task(_sub(s)) for s in self.listens]
        self.log.info("agent.started", listens=list(self.listens), publishes=list(self.publishes))
        await asyncio.gather(*tasks)

    async def _safe_handle(self, event: Event) -> None:
        try:
            await self.handle(event)
        except Exception as e:
            self.log.exception(
                "agent.handle_failed",
                event_type=event.event_type,
                error=str(e),
            )
            raise

    @abstractmethod
    async def handle(self, event: Event) -> None: ...
