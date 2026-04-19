"""Corpus bootstrapping for evaluation.

Each dataset may ship a ``corpus/`` directory of plain-text documents that
must be ingested before the questions can be answered. This module drives
the normal ingest → segment → enrich → graph_written pipeline in-memory
using :class:`InMemoryBus` + the caller-provided graph store.

This is what makes the evaluation runner reproducible without a live
Neo4j / MinIO stack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.svc_enrich.agent import EnrichAgent
from services.svc_graph_write.agent import GraphWriterAgent
from services.svc_ingest.agent import IngestAgent
from services.svc_segment.agent import SegmentAgent
from ..bus.factory import Streams
from ..bus.memory import InMemoryBus
from ..core import get_logger, settings
from ..data_models.events import IngestRequestEvent
from ..data_models.metadata import DocumentKind, DocumentMetadata
from ..data_models.provenance import sha256_bytes
from ..graph import GraphWriter
from ..storage import storage_key_for
from ..storage.base import ObjectStore


log = get_logger("eval.bootstrap")


async def bootstrap_dataset(
    *,
    corpus_dir: Path,
    object_store: ObjectStore,
    graph_store: Any,
    matter_id: str | None = None,
) -> int:
    """Ingest every ``*.txt`` / ``*.md`` / ``*.html`` file under ``corpus_dir``.

    Returns the number of files processed. Files are routed to the public
    bucket when ``matter_id`` is ``None`` and to the private bucket otherwise.
    """
    if not corpus_dir.exists():
        log.info("bootstrap.no_corpus", dir=str(corpus_dir))
        return 0

    bus = InMemoryBus()
    ingest = IngestAgent(bus=bus)
    segment = SegmentAgent(bus=bus)
    enrich = EnrichAgent(bus=bus)
    writer = GraphWriterAgent(bus=bus)

    for ag in (ingest, segment, writer):
        ag.writer = GraphWriter(neo=graph_store)  # type: ignore[arg-type]

    bucket = (
        settings.minio_bucket_private if matter_id else settings.minio_bucket_public
    )
    count = 0

    for path in sorted(corpus_dir.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in {".txt", ".md", ".html"}:
            continue
        data = path.read_bytes()
        sha = sha256_bytes(data)
        key = storage_key_for(
            prefix=matter_id or "eval",
            sha256=sha,
            filename=path.name,
        )
        await object_store.put_object(
            bucket=bucket,
            key=key,
            data=data,
            content_type="text/plain",
        )
        meta = DocumentMetadata(
            filename=path.name,
            matter_id=matter_id,
            kind=_infer_kind(path.name),
            confidentiality="private" if matter_id else "public",
        )
        evt = IngestRequestEvent(
            trace_id=f"eval-{sha[:8]}",
            matter_id=matter_id,
            source="upload",
            upload_uri=f"s3://{bucket}/{key}",
            upload_bucket=bucket,
            upload_key=key,
            upload_filename=path.name,
            upload_mime="text/plain",
            upload_sha256=sha,
            upload_size=len(data),
            metadata=meta,
        )
        await bus.publish(Streams.INGEST_REQUEST, evt)
        count += 1

    # Drain each stream until quiescent. ``expected=count`` is a lower bound;
    # enrich/writer may be invoked once per ingest event.
    await bus.drain(Streams.INGEST_REQUEST, ingest._safe_handle, expected=count)
    await bus.drain(Streams.INGEST_COMPLETED, segment._safe_handle, expected=count)
    await bus.drain(Streams.SEGMENT_COMPLETED, enrich._safe_handle, expected=count)
    await bus.drain(Streams.ENRICH_COMPLETED, writer._safe_handle, expected=count)
    log.info("bootstrap.done", files=count, matter_id=matter_id)
    return count


def _infer_kind(name: str) -> DocumentKind:
    low = name.lower()
    if any(k in low for k in ("judgment", "judgement", "sci_", "hc_", "case")):
        return DocumentKind.JUDGMENT
    if any(k in low for k in ("fir_",)):
        return DocumentKind.FIR
    if any(k in low for k in ("chargesheet",)):
        return DocumentKind.CHARGESHEET
    if any(k in low for k in ("contract", "agreement")):
        return DocumentKind.CONTRACT
    return DocumentKind.STATUTE
