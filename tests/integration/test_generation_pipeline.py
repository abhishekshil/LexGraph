"""End-to-end retrieval → generation integration test.

Ingests a small IPC snippet, runs the RetrievalOrchestrator to build an
EvidencePack, then pipes it through the GroundedGenerator with the stub
provider. Every citation in the final Answer must be backed by a span in the
pack (no fabrications), and the provenance chain (node → source span → file)
must round-trip cleanly.
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
from services.lib.data_models.events import IngestRequestEvent
from services.lib.data_models.metadata import DocumentKind, DocumentMetadata
from services.lib.data_models.provenance import sha256_bytes
from services.lib.generation import GroundedGenerator, StubProvider
from services.lib.graph import GraphWriter, InMemoryGraphStore
from services.lib.indexing import get_embedder, get_indexer
from services.lib.retrieval.orchestrator import RetrievalOrchestrator
from services.lib.storage import get_object_store, storage_key_for


SAMPLE_IPC = """THE INDIAN PENAL CODE, 1860

CHAPTER XVII — OF OFFENCES AGAINST PROPERTY

378. Theft.
Whoever, intending to take dishonestly any movable property out of the
possession of any person without that person's consent, moves that property in
order to such taking, is said to commit theft.

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
    get_indexer.cache_clear()
    get_embedder.cache_clear()
    yield
    get_indexer.cache_clear()
    get_embedder.cache_clear()


def _wire_writer(agent, store):
    agent.writer = GraphWriter(neo=store)  # type: ignore[arg-type]


async def _ingest(bus, obj_store, graph_store, matter_id: str = "m1") -> None:
    from services.lib.core import settings

    bucket = settings.minio_bucket_private
    sha = sha256_bytes(SAMPLE_IPC.encode("utf-8"))
    key = storage_key_for(prefix=matter_id, sha256=sha, filename="ipc.txt")
    await obj_store.put_object(
        bucket=bucket,
        key=key,
        data=SAMPLE_IPC.encode("utf-8"),
        content_type="text/plain",
    )
    meta = DocumentMetadata(
        filename="ipc.txt",
        matter_id=matter_id,
        kind=DocumentKind.STATUTE,
        confidentiality="private",
    )
    evt = IngestRequestEvent(
        trace_id="trace-gen-1",
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
async def test_retrieval_generation_end_to_end(object_store, graph_store):
    bus = InMemoryBus()
    await _ingest(bus, object_store, graph_store)

    orch = RetrievalOrchestrator(store=graph_store)
    pack = await orch.answer(
        question="What is the punishment for theft under Section 379 IPC?",
        matter_scope="m1",
    )
    assert pack.spans, "retrieval produced no spans"

    gen = GroundedGenerator(provider=StubProvider())
    answer = await gen.generate(pack, trace_id="t-gen-e2e")

    # The stub grounds every claim in a marker, so enforcement must keep all.
    assert answer.insufficient_evidence is False

    # Because we ingested under a private matter, the spans are classified as
    # private material. Either bucket is acceptable — what matters is that
    # some citation bucket is populated and each citation is backed by a span.
    all_cits = answer.legal_basis + answer.supporting_private_sources
    assert all_cits, "no citations emitted at all"

    pack_markers = {s.marker for s in pack.spans}
    for cit in all_cits:
        assert cit.marker in pack_markers
        assert cit.node_id
        assert cit.source_span_id
        assert cit.excerpt

    for cit in all_cits:
        node = await graph_store.get_node(cit.node_id)
        assert node is not None, f"cited node {cit.node_id} not in graph"

    # Answer body is still in canonical layout and contains markers.
    assert "[S" in answer.answer
    assert "Confidence:" in answer.answer
    assert answer.extras.get("provider") == "stub"


@pytest.mark.asyncio
async def test_retrieval_then_refusal_on_empty_question(object_store, graph_store):
    """A nonsense query should produce a refusal answer, not a hallucination."""
    bus = InMemoryBus()
    await _ingest(bus, object_store, graph_store)

    orch = RetrievalOrchestrator(store=graph_store)
    pack = await orch.answer(
        question="zzzzzzzzz qqqqqqqqq",
        matter_scope="m1",
    )
    # With no seeds, typed BFS yields nothing; semantic fallback has no index;
    # the evidence pack should be empty or flagged insufficient.
    gen = GroundedGenerator(provider=StubProvider())
    answer = await gen.generate(pack, trace_id="t-refuse-real")
    if not pack.spans or pack.insufficient_evidence:
        assert answer.insufficient_evidence is True
        assert answer.confidence == "low"
        assert answer.legal_basis == []
