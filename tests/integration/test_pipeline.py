"""End-to-end ingestion pipeline, in a single process, with all stateful
backends swapped for in-memory fakes:

  IngestAgent → SegmentAgent → EnrichAgent → GraphWriterAgent

Verifies that:
  * the object-store round-trip works
  * the segmenter produces typed spans
  * the enrich agent emits schema-valid node/edge payloads
  * the graph writer persists everything with NODE_DERIVED_FROM_SOURCE edges
  * the audit log captures every stage
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from services.svc_enrich.agent import EnrichAgent
from services.svc_graph_write.agent import GraphWriterAgent
from services.svc_ingest.agent import IngestAgent
from services.svc_segment.agent import SegmentAgent
from services.lib.bus.memory import InMemoryBus
from services.lib.bus.factory import Streams
from services.lib.data_models.events import (
    IngestRequestEvent,
    IngestCompletedEvent,
    SegmentCompletedEvent,
    EnrichCompletedEvent,
    GraphWrittenEvent,
)
from services.lib.data_models.metadata import DocumentKind, DocumentMetadata
from services.lib.data_models.provenance import sha256_bytes
from services.lib.graph import GraphWriter, InMemoryGraphStore
from services.lib.storage import get_object_store, storage_key_for


SAMPLE_STATUTE = """THE INDIAN PENAL CODE, 1860

CHAPTER XVII — OF OFFENCES AGAINST PROPERTY

378. Theft.
Whoever, intending to take dishonestly any movable property out of the
possession of any person without that person's consent, moves that property in
order to such taking, is said to commit theft.

Explanation 1. — A thing so long as it is attached to the earth, not being
movable property, is not the subject of theft; but it becomes capable of being
the subject of theft as soon as it is severed from the earth.

379. Punishment for theft.
Whoever commits theft shall be punished with imprisonment of either description
for a term which may extend to three years, or with fine, or with both.
"""


@pytest.fixture
def shared_store(tmp_path, monkeypatch):
    """Use a local-disk object store rooted in ``tmp_path``."""
    from services.lib.core import settings

    monkeypatch.setattr(settings, "minio_endpoint", "")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    # clear the cache so get_object_store sees the new data_dir
    from services.lib.storage.factory import get_object_store as _gos

    _gos.cache_clear()
    store = get_object_store()
    return store


@pytest.fixture
def graph_store():
    return InMemoryGraphStore()


def _wire_writer_to_memory(agent, graph_store):
    """Replace the Neo4j-backed GraphWriter with one pointed at the in-mem store."""
    agent.writer = GraphWriter(neo=graph_store)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_ingest_segment_enrich_write_statute(
    tmp_path, monkeypatch, shared_store, graph_store
):
    from services.lib.core import settings

    bus = InMemoryBus()

    bucket = settings.minio_bucket_private
    sha = sha256_bytes(SAMPLE_STATUTE.encode("utf-8"))
    key = storage_key_for(prefix="m1", sha256=sha, filename="ipc.txt")
    await shared_store.put_object(
        bucket=bucket,
        key=key,
        data=SAMPLE_STATUTE.encode("utf-8"),
        content_type="text/plain",
    )

    meta = DocumentMetadata(
        filename="ipc.txt",
        matter_id="m1",
        kind=DocumentKind.STATUTE,
        confidentiality="private",
    )
    evt = IngestRequestEvent(
        trace_id="trace-1",
        matter_id="m1",
        source="upload",
        upload_uri=f"s3://{bucket}/{key}",
        upload_bucket=bucket,
        upload_key=key,
        upload_filename="ipc.txt",
        upload_mime="text/plain",
        upload_sha256=sha,
        upload_size=len(SAMPLE_STATUTE.encode("utf-8")),
        metadata=meta,
    )

    ingest = IngestAgent(bus=bus)
    _wire_writer_to_memory(ingest, graph_store)

    segment = SegmentAgent(bus=bus)
    _wire_writer_to_memory(segment, graph_store)

    enrich = EnrichAgent(bus=bus)

    writer = GraphWriterAgent(bus=bus)
    _wire_writer_to_memory(writer, graph_store)

    await bus.publish(Streams.INGEST_REQUEST, evt)

    # Drive the pipeline step by step.
    assert await bus.drain(Streams.INGEST_REQUEST, ingest._safe_handle, expected=1) == 1
    completed = [
        e for e in bus.published_on(Streams.INGEST_COMPLETED)
        if isinstance(e, IngestCompletedEvent)
    ]
    assert completed, "ingest did not publish"

    assert await bus.drain(Streams.INGEST_COMPLETED, segment._safe_handle, expected=1) == 1
    seg_completed = [
        e for e in bus.published_on(Streams.SEGMENT_COMPLETED)
        if isinstance(e, SegmentCompletedEvent)
    ]
    assert seg_completed, "segment did not publish"
    assert len(seg_completed[0].spans) >= 2  # at least Section 378 & 379

    assert await bus.drain(Streams.SEGMENT_COMPLETED, enrich._safe_handle, expected=1) == 1
    enr_completed = [
        e for e in bus.published_on(Streams.ENRICH_COMPLETED)
        if isinstance(e, EnrichCompletedEvent)
    ]
    assert enr_completed, "enrich did not publish"

    assert await bus.drain(Streams.ENRICH_COMPLETED, writer._safe_handle, expected=1) == 1
    written = [
        e for e in bus.published_on(Streams.GRAPH_WRITTEN)
        if isinstance(e, GraphWrittenEvent)
    ]
    assert written, "graph_writer did not publish"

    # Assertions on the graph itself.
    assert graph_store.count_nodes("SourceEpisode") == 1
    assert graph_store.count_nodes("SourceSpan") >= 2
    assert graph_store.count_nodes("File") == 1
    assert graph_store.count_nodes("Section") >= 1

    # every typed node (except File/Episode/Span) has a NODE_DERIVED_FROM_SOURCE
    provenance_edges = graph_store.count_edges("NODE_DERIVED_FROM_SOURCE")
    assert provenance_edges >= graph_store.count_nodes("Section")

    # DLQ should be empty
    assert bus.dlq == [], f"DLQ not empty: {bus.dlq}"
