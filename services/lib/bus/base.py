"""Event-bus contract. Backends (Redis Streams, Kafka, in-memory) implement this."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable

from ..data_models.events import Event


EventHandler = Callable[[Event], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, stream: str, event: Event) -> str:
        """Publish `event` to `stream`. Returns backend-specific message id."""

    @abstractmethod
    async def subscribe(
        self,
        stream: str,
        *,
        group: str,
        consumer: str,
        handler: EventHandler,
        block_ms: int = 5000,
    ) -> None:
        """Long-running consumer loop. Creates group if missing. Acks after handler."""

    @abstractmethod
    async def dead_letter(self, stream: str, event: Event, reason: str) -> None:
        """Route a poisoned event to a DLQ stream named `<stream>.dlq`."""

    @abstractmethod
    async def close(self) -> None: ...
