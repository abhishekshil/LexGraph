"""Per-trace, in-process event bus for live agent-trace streaming.

Why in-process, not Redis?
    The API gateway executes the entire query flow itself (classify →
    seeds → graph BFS → Graphiti search → rank → evidence → generate).
    Shipping those steps through Redis just to deliver them back to the
    same process adds latency and failure modes for no benefit. The bus
    keeps a bounded history so that a client who subscribes slightly
    *after* the query starts still receives the preceding steps.

Usage:

    # In the request handler
    tid = f"trace_{uuid4().hex}"
    with trace_scope(tid):
        await emit_step("query.received", status="start", question=q)
        pack = await orch.answer(...)
        await emit_step("answer.ready", status="done",
                        spans=len(pack.spans))

    # Concurrently, the SSE generator
    async for event in get_bus().stream(tid):
        yield f"data: {json.dumps(event)}\\n\\n"
        if event.get("status") == "end":
            break

The ``ContextVar`` lets instrumentation code deep inside the retrieval
stack emit steps without having to thread a ``trace_id`` argument
through every helper signature.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import time
from collections import deque
from typing import Any, AsyncIterator, Iterator


_current_trace_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "lexgraph_trace_id", default=None
)


class TraceBus:
    """Multi-subscriber bus with per-trace bounded history.

    The bus retains the last ``history_size`` events per trace so that a
    client that subscribes mid-query still sees the steps that already
    executed. Traces older than ``max_age_sec`` are garbage-collected to
    keep memory bounded under load.
    """

    def __init__(self, *, history_size: int = 512, max_age_sec: int = 900) -> None:
        self._history: dict[str, deque[dict[str, Any]]] = {}
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._last_touch: dict[str, float] = {}
        self._history_size = history_size
        self._max_age_sec = max_age_sec

    def publish(self, trace_id: str, event: dict[str, Any]) -> None:
        event = {"ts": time.time(), **event}
        self._gc()
        hist = self._history.setdefault(
            trace_id, deque(maxlen=self._history_size)
        )
        hist.append(event)
        self._last_touch[trace_id] = time.time()
        for q in list(self._subscribers.get(trace_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def subscribe(self, trace_id: str) -> asyncio.Queue[dict[str, Any]]:
        """Return a fresh queue pre-loaded with the trace's event history.

        Callers own the queue and should pass it to :meth:`unsubscribe`
        when finished. This is the low-level API used by the SSE handler,
        which races the queue against the background query task to
        terminate promptly when the pipeline completes.
        """
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1024)
        for e in list(self._history.get(trace_id, ())):
            q.put_nowait(e)
        self._subscribers.setdefault(trace_id, []).append(q)
        return q

    def unsubscribe(
        self, trace_id: str, q: asyncio.Queue[dict[str, Any]]
    ) -> None:
        subs = self._subscribers.get(trace_id, [])
        if q in subs:
            subs.remove(q)

    async def stream(
        self, trace_id: str, *, idle_timeout: float = 60.0
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield every event for ``trace_id``, including any already buffered.

        Terminates when an event with ``status == "end"`` arrives, or when
        no event is produced for ``idle_timeout`` seconds (keeps idle
        clients from pinning the bus forever).
        """
        q = self.subscribe(trace_id)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=idle_timeout)
                except asyncio.TimeoutError:
                    return
                yield event
                if event.get("status") == "end":
                    return
        finally:
            self.unsubscribe(trace_id, q)

    def _gc(self) -> None:
        cutoff = time.time() - self._max_age_sec
        to_drop = [
            tid for tid, ts in list(self._last_touch.items()) if ts < cutoff
        ]
        for tid in to_drop:
            self._last_touch.pop(tid, None)
            self._history.pop(tid, None)
            # Leave subscribers alone — they'll terminate on idle timeout.


_BUS = TraceBus()


def get_bus() -> TraceBus:
    return _BUS


def get_trace_id() -> str | None:
    return _current_trace_id.get()


def set_trace_id(trace_id: str) -> contextvars.Token:
    return _current_trace_id.set(trace_id)


@contextlib.contextmanager
def trace_scope(trace_id: str) -> Iterator[None]:
    token = _current_trace_id.set(trace_id)
    try:
        yield
    finally:
        _current_trace_id.reset(token)


async def emit_step(
    stage: str,
    *,
    status: str = "info",
    worker: str = "api",
    message: str | None = None,
    **details: Any,
) -> None:
    """Publish a trace step for the current context's trace_id.

    Silently becomes a no-op when no trace_id is set (e.g. the regular
    non-streaming ``/api/query`` endpoint), so instrumentation is safe to
    leave in the hot path. ``status`` conventions used by the UI:

    - ``start``     — a stage began; usually paired with a later ``done``.
    - ``done``      — stage finished successfully.
    - ``info``      — single-shot informational event (no paired end).
    - ``warn``      — recoverable issue; stage continues.
    - ``error``     — stage failed; usually paired with an ``end`` below.
    - ``end``       — terminal sentinel; the SSE stream closes when seen.
    """
    tid = _current_trace_id.get()
    if not tid:
        return
    event = {
        "stage": stage,
        "status": status,
        "worker": worker,
    }
    if message is not None:
        event["message"] = message
    if details:
        event["details"] = details
    _BUS.publish(tid, event)
    # Yield control so the subscriber's queue consumer can flush the event
    # out to the client promptly even when the publisher is bursty.
    await asyncio.sleep(0)
