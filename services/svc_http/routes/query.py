from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator
from uuid import uuid4

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ...lib.core import get_logger, settings
from ...lib.data_models.answer import Answer
from ...lib.generation import GroundedGenerator
from ...lib.observability import emit_step, get_bus, trace_scope
from ...lib.retrieval import RetrievalOrchestrator


log = get_logger("api.query")

router = APIRouter(prefix="/query", tags=["query"])


class QueryRequest(BaseModel):
    question: str
    matter_scope: str | None = None
    mode: str | None = None   # graph_only | graph_plus_semantic | graph_plus_semantic_plus_rerank


@router.post("", response_model=Answer)
async def query(body: QueryRequest) -> Answer:
    """Non-streaming query endpoint (backwards-compatible)."""
    orch = RetrievalOrchestrator()
    pack = await orch.answer(
        question=body.question,
        matter_scope=body.matter_scope,
        mode=body.mode or settings.retrieval_mode,
    )
    gen = GroundedGenerator()
    return await gen.generate(pack, trace_id=f"trace_{uuid4().hex}")


@router.post("/stream")
async def query_stream(body: QueryRequest) -> StreamingResponse:
    """Stream the full agent trace over Server-Sent Events.

    The client receives one JSON event per line with ``data:`` prefix::

        data: {"stage":"query.received","status":"start",...}
        data: {"stage":"intent.classify","status":"done",...}
        ...
        data: {"stage":"answer.ready","status":"end","answer":{...}}

    The final event always has ``status == "end"`` and carries either the
    full :class:`Answer` payload or an ``error`` field. The UI uses this
    to render a live agent-trace timeline alongside the final answer.
    """
    trace_id = f"trace_{uuid4().hex}"
    return StreamingResponse(
        _event_stream(body, trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # disable proxy buffering (nginx/ingress)
            "Connection": "keep-alive",
            "X-Trace-Id": trace_id,
        },
    )


async def _event_stream(
    body: QueryRequest, trace_id: str
) -> AsyncIterator[bytes]:
    bus = get_bus()

    # Kick off the query as a background task so the bus subscriber and
    # the workload run concurrently; any step emitted from within the
    # workload is delivered to the subscriber in near-real-time.
    task: asyncio.Task[Answer | None] = asyncio.create_task(
        _run_query(body, trace_id)
    )

    yield _sse({
        "stage": "trace.open",
        "status": "info",
        "worker": "api",
        "trace_id": trace_id,
        "message": "Trace stream opened",
    })

    # Manually subscribe so we can race the queue against the background
    # task's completion and terminate the stream as soon as the pipeline
    # is done, instead of waiting for an idle timeout.
    q = bus.subscribe(trace_id)
    try:
        while True:
            get_task = asyncio.create_task(q.get())
            done, _pending = await asyncio.wait(
                {get_task, task},
                return_when=asyncio.FIRST_COMPLETED,
                timeout=120.0,
            )
            if get_task in done:
                yield _sse(get_task.result())
                continue
            # task finished (or idle timeout); cancel the pending get and
            # flush any still-queued events before closing the stream.
            get_task.cancel()
            while not q.empty():
                yield _sse(q.get_nowait())
            break
    except asyncio.CancelledError:
        task.cancel()
        raise
    finally:
        bus.unsubscribe(trace_id, q)
        # Surface the final Answer (or error) as the terminal event so
        # the client doesn't need a second round-trip.
        try:
            answer = await task
        except Exception as e:  # noqa: BLE001
            log.warning("query.stream.task_failed", error=str(e), trace_id=trace_id)
            yield _sse({
                "stage": "answer.ready",
                "status": "end",
                "worker": "api",
                "error": str(e),
                "trace_id": trace_id,
            })
            return
        if answer is not None:
            yield _sse({
                "stage": "answer.ready",
                "status": "end",
                "worker": "api",
                "trace_id": trace_id,
                "answer": answer.model_dump(mode="json"),
            })


async def _run_query(body: QueryRequest, trace_id: str) -> Answer | None:
    """Execute the query pipeline under a trace scope so every instrumented
    helper automatically publishes to this trace's event stream."""
    with trace_scope(trace_id):
        try:
            await emit_step(
                "query.received",
                status="start",
                worker="api",
                message=f"Query received (mode={body.mode or settings.retrieval_mode})",
                question=body.question,
                matter_scope=body.matter_scope,
                mode=body.mode or settings.retrieval_mode,
            )
            orch = RetrievalOrchestrator()
            pack = await orch.answer(
                question=body.question,
                matter_scope=body.matter_scope,
                mode=body.mode or settings.retrieval_mode,
            )
            gen = GroundedGenerator()
            answer = await gen.generate(pack, trace_id=trace_id)
            await emit_step(
                "query.done",
                status="done",
                worker="api",
                message=(
                    "Refused (insufficient evidence)"
                    if answer.insufficient_evidence
                    else f"Grounded answer · confidence={answer.confidence}"
                ),
                confidence=answer.confidence,
                insufficient=answer.insufficient_evidence,
                citations=len(answer.legal_basis),
            )
            return answer
        except Exception as e:  # noqa: BLE001
            log.exception("query.stream.pipeline_failed")
            await emit_step(
                "query.error",
                status="error",
                worker="api",
                message=f"Pipeline failed: {e}",
                error=str(e),
            )
            raise


def _sse(event: dict[str, Any]) -> bytes:
    """Encode a JSON event as a single SSE frame."""
    return f"data: {json.dumps(event, default=str)}\n\n".encode("utf-8")
