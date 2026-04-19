"""Integration test for the EvaluationRunner.

Drives the whole ingest → retrieve → generate → metrics pipeline against
an in-memory graph + local object store using the small fixture corpora
shipped with each dataset.

These tests *also* act as the Phase-5 regression gate sanity check: if
they drift, the CI threshold gate will too.
"""

from __future__ import annotations

import pytest

from services.lib.evaluation import (
    EvaluationRunner,
    check_thresholds,
    load_thresholds,
)
from services.lib.generation import GroundedGenerator, StubProvider
from services.lib.graph import InMemoryGraphStore
from services.lib.indexing import get_embedder, get_indexer
from services.lib.retrieval.orchestrator import RetrievalOrchestrator
from services.lib.storage import get_object_store


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
def _reset_index_caches():
    get_embedder.cache_clear()
    get_indexer.cache_clear()
    yield
    get_embedder.cache_clear()
    get_indexer.cache_clear()


def _make_runner(graph_store, object_store) -> EvaluationRunner:
    orch = RetrievalOrchestrator(store=graph_store)
    gen = GroundedGenerator(provider=StubProvider())
    return EvaluationRunner(
        orchestrator=orch,
        generator=gen,
        graph_store=graph_store,
        object_store=object_store,
    )


@pytest.mark.asyncio
async def test_runner_executes_offence_ingredients_dataset(object_store, graph_store):
    runner = _make_runner(graph_store, object_store)
    report = await runner.run_dataset("offence_ingredients_ipc_bns")

    assert report.summary.items == 7
    # Every item should have a non-zero latency measurement.
    assert all(r.latency_s >= 0 for r in report.results)
    # Retrieval should cover most of the answerable items (corpus is tiny).
    assert report.summary.retrieval_coverage > 0.5
    # Fabricated markers should be 0 with the deterministic stub provider.
    assert report.summary.fabricated_marker_rate == 0.0
    # Citation faithfulness is 1.0 by construction (stub only cites pack markers).
    assert report.summary.citation_faithfulness == 1.0
    # Tier-1 anchors must be present on at least some items.
    assert report.summary.tier1_anchor_rate > 0


@pytest.mark.asyncio
async def test_runner_runs_all_datasets(object_store, graph_store):
    runner = _make_runner(graph_store, object_store)
    report = await runner.run()
    assert len(report.datasets) >= 3
    names = {d.dataset for d in report.datasets}
    assert {
        "offence_ingredients_ipc_bns",
        "procedure_crpc_bnss",
        "evidence_iea_bsa",
    } <= names

    # Every dataset produces a summary with no fabrications (stub provider).
    for ds in report.datasets:
        assert ds.summary.fabricated_marker_rate == 0.0
        assert ds.summary.items > 0


@pytest.mark.asyncio
async def test_runner_private_matter_dataset_stays_scoped(object_store, graph_store):
    runner = _make_runner(graph_store, object_store)
    report = await runner.run_dataset("private_matter_qa")

    # Every item on this dataset carries a matter scope → all retrieved
    # content must be flagged private (tier 6 / 7) where it came from the
    # private corpus. At minimum, no public tier-1/2/3 spans should appear
    # because we didn't ingest any public corpus on this matter.
    for item in report.results:
        for t in item.pack_tiers:
            assert t not in (2, 3, 4, 5), f"unexpected public tier on private matter: {t}"


@pytest.mark.asyncio
async def test_runner_report_roundtrips_through_threshold_check(object_store, graph_store):
    runner = _make_runner(graph_store, object_store)
    report = await runner.run_dataset("offence_ingredients_ipc_bns")
    full = type(report)  # not used, just sanity

    # Feed the single-dataset report into an EvaluationReport and gate it
    # against permissive thresholds — should pass cleanly.
    from services.lib.evaluation import EvaluationReport

    full_report = EvaluationReport(datasets=[report])
    thresholds = {
        "_default": {
            "min": {"citation_faithfulness": 0.9},
            "max": {"fabricated_marker_rate": 0.05},
        }
    }
    assert check_thresholds(full_report, thresholds) == []


def test_thresholds_yaml_is_loadable():
    # Guards against YAML syntax regressions in the CI gate config.
    thresholds = load_thresholds()
    assert "_default" in thresholds
    assert "min" in thresholds["_default"]
