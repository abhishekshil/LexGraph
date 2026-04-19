"""End-to-end retrieval pipeline with all backends in-memory.

Exercises:
    IngestAgent -> SegmentAgent -> EnrichAgent -> GraphWriterAgent -> IndexAgent

and then:
    RetrievalOrchestrator.answer(...)

using the :class:`InMemoryGraphStore` as the graph backend and the
:class:`QdrantIndexer` auto-falling-back to its pure-Python index.
"""

from __future__ import annotations

import pytest

from services.svc_enrich.agent import EnrichAgent
from services.svc_graph_write.agent import GraphWriterAgent
from services.svc_index.agent import IndexAgent
from services.svc_ingest.agent import IngestAgent
from services.svc_segment.agent import SegmentAgent
from services.lib.bus.factory import Streams
from services.lib.bus.memory import InMemoryBus
from services.lib.data_models.events import (
    EnrichCompletedEvent,
    GraphWrittenEvent,
    IndexCompletedEvent,
    IngestCompletedEvent,
    IngestRequestEvent,
    SegmentCompletedEvent,
)
from services.lib.data_models.metadata import DocumentKind, DocumentMetadata
from services.lib.data_models.provenance import sha256_bytes
from services.lib.graph import GraphWriter, InMemoryGraphStore
from services.lib.indexing import get_embedder, get_indexer
from services.lib.retrieval.orchestrator import RetrievalOrchestrator
from services.lib.retrieval.seeds import find_seed_nodes
from services.lib.storage import get_object_store, storage_key_for


SAMPLE_IPC = """THE INDIAN PENAL CODE, 1860

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
def object_store(tmp_path, monkeypatch):
    from services.lib.core import settings
    from services.lib.storage.factory import get_object_store as _gos

    monkeypatch.setattr(settings, "minio_endpoint", "")
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    _gos.cache_clear()
    return get_object_store()


@pytest.fixture
def graph_store():
    return InMemoryGraphStore()


@pytest.fixture(autouse=True)
def _reset_indexing_caches():
    # Make sure every test starts with a clean embedder + Qdrant fallback.
    get_indexer.cache_clear()
    get_embedder.cache_clear()
    yield
    get_indexer.cache_clear()
    get_embedder.cache_clear()


def _wire_writer(agent, store):
    agent.writer = GraphWriter(neo=store)  # type: ignore[arg-type]


async def _ingest_corpus(bus, store, graph_store, matter_id="m1"):
    from services.lib.core import settings

    bucket = settings.minio_bucket_private
    sha = sha256_bytes(SAMPLE_IPC.encode("utf-8"))
    key = storage_key_for(prefix=matter_id, sha256=sha, filename="ipc.txt")
    await store.put_object(
        bucket=bucket, key=key, data=SAMPLE_IPC.encode("utf-8"), content_type="text/plain"
    )

    meta = DocumentMetadata(
        filename="ipc.txt",
        matter_id=matter_id,
        kind=DocumentKind.STATUTE,
        confidentiality="private",
    )
    evt = IngestRequestEvent(
        trace_id="trace-ret-1",
        matter_id=matter_id,
        source="upload",
        upload_uri=f"s3://{bucket}/{key}",
        upload_bucket=bucket,
        upload_key=key,
        upload_filename="ipc.txt",
        upload_mime="text/plain",
        upload_sha256=sha,
        upload_size=len(SAMPLE_IPC.encode("utf-8")),
        metadata=meta,
    )

    ingest = IngestAgent(bus=bus); _wire_writer(ingest, graph_store)
    segment = SegmentAgent(bus=bus); _wire_writer(segment, graph_store)
    enrich = EnrichAgent(bus=bus)
    writer = GraphWriterAgent(bus=bus); _wire_writer(writer, graph_store)
    indexer = IndexAgent(bus=bus)

    await bus.publish(Streams.INGEST_REQUEST, evt)
    assert await bus.drain(Streams.INGEST_REQUEST, ingest._safe_handle, expected=1) == 1
    assert await bus.drain(Streams.INGEST_COMPLETED, segment._safe_handle, expected=1) == 1
    assert await bus.drain(Streams.SEGMENT_COMPLETED, enrich._safe_handle, expected=1) == 1
    assert await bus.drain(Streams.ENRICH_COMPLETED, writer._safe_handle, expected=1) == 1
    assert await bus.drain(Streams.GRAPH_WRITTEN, indexer._safe_handle, expected=1) == 1


@pytest.mark.asyncio
async def test_canonical_section_ids_are_emitted(object_store, graph_store):
    bus = InMemoryBus()
    await _ingest_corpus(bus, object_store, graph_store)

    # Canonical Act + Sections
    assert await graph_store.get_node("act:ipc") is not None
    assert await graph_store.get_node("section:ipc:378") is not None
    assert await graph_store.get_node("section:ipc:379") is not None

    # Provenance edges exist for those sections
    assert graph_store.count_edges("NODE_DERIVED_FROM_SOURCE") >= 3


@pytest.mark.asyncio
async def test_index_agent_publishes_and_fills_index(object_store, graph_store):
    bus = InMemoryBus()
    await _ingest_corpus(bus, object_store, graph_store)

    idx_done = [
        e for e in bus.published_on(Streams.INDEX_COMPLETED)
        if isinstance(e, IndexCompletedEvent)
    ]
    assert idx_done, "index.completed was not published"
    evt = idx_done[0]
    # Private matter ingest should go only to the private collection.
    assert evt.collection_private >= 2
    assert evt.collection_public == 0
    assert evt.upserted == evt.collection_private + evt.collection_public


@pytest.mark.asyncio
async def test_seeds_resolve_section_refs(object_store, graph_store):
    bus = InMemoryBus()
    await _ingest_corpus(bus, object_store, graph_store)

    seeds = await find_seed_nodes(
        "What does Section 378 IPC say about theft?",
        store=graph_store,
        matter_scope="m1",
    )
    assert "section:ipc:378" in seeds.node_ids
    assert any(r.startswith("section_ref:") for r in seeds.reasons)


@pytest.mark.asyncio
async def test_retrieval_end_to_end_produces_grounded_pack(object_store, graph_store):
    bus = InMemoryBus()
    await _ingest_corpus(bus, object_store, graph_store)

    orch = RetrievalOrchestrator(store=graph_store)
    pack = await orch.answer(
        question="What is the punishment for theft under Section 379 IPC?",
        matter_scope="m1",
    )

    assert pack.spans, "no spans produced"
    # Every span must have traceable provenance.
    for s in pack.spans:
        assert s.node_id
        assert s.source_span_id
        assert s.excerpt
        assert int(s.tier) >= 1

    # The intent classifier should pick either punishment / statute_lookup.
    assert pack.query_type in {"punishment_lookup", "statute_lookup", "generic"}

    # Section 379 should be the (or a) primary seed.
    assert any(
        r.startswith("section_ref:") and "379" in r
        for r in pack.intent.get("seed_reasons", [])
    )

    # Insufficient_evidence must be False because we have at least one tier-1
    # statute span.
    assert not pack.insufficient_evidence
    assert any(int(s.tier) == 1 for s in pack.spans)


@pytest.mark.asyncio
async def test_matter_isolation(object_store, graph_store):
    """A public query (no matter_scope) must not surface private nodes."""
    bus = InMemoryBus()
    await _ingest_corpus(bus, object_store, graph_store, matter_id="private-m1")

    orch = RetrievalOrchestrator(store=graph_store)
    pack = await orch.answer(
        question="What is theft under Section 378 IPC?",
        matter_scope=None,
    )
    # No private matter nodes (they all have matter_id="private-m1") should
    # appear in the pack.
    for s in pack.spans:
        assert s.matter_id is None, f"private span leaked: {s.node_id}"
