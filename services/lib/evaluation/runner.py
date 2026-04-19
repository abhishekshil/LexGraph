"""Evaluation runner — iterates a dataset, drives the retrieval + generation
pipeline, and aggregates metrics.

Design notes
------------

* The runner is DI-friendly: pass ``store`` / ``object_store`` / ``orchestrator``
  / ``generator`` and you can evaluate against the in-memory stack (used by
  tests and by the CI regression gate in ``scripts/run_eval.py``).

* Each dataset lives under ``services/evaluation/datasets/<name>/`` and ships:

  * ``items.jsonl``   — one question per line with ``id``, ``question``, and
                         optional ``matter_scope``.
  * ``gold.jsonl``    — aligned gold labels (``expected_mapping``,
                         ``expected_sections``, ``expected_node_ids`` …).
                         Missing gold for an id means "unanswerable — refuse".
  * ``corpus/``       — optional ``*.txt`` files the runner ingests before
                         evaluating. Needed for reproducible local runs.

* The runner returns a :class:`DatasetReport` or :class:`EvaluationReport`
  with full per-item results + aggregated metrics.
"""

from __future__ import annotations

import datetime as dt
import json
import time
from pathlib import Path
from typing import Any

from ..core import get_logger, settings
from ..generation import GroundedGenerator
from ..retrieval.orchestrator import RetrievalOrchestrator
from ..storage.base import ObjectStore
from .metrics import (
    citation_faithfulness,
    crosswalk_mapping_accuracy,
    fabricated_marker_rate,
    false_refusal_rate,
    grounding_rate,
    latency_stats,
    pack_utilisation,
    refusal_rate,
    retrieval_coverage,
    retrieval_hit_rate,
    span_citation_correctness,
    tier1_anchor_rate,
    true_refusal_rate,
    unsupported_claim_rate,
)
from .report import (
    DatasetReport,
    EvaluationReport,
    EvaluationSummary,
    ItemResult,
)


log = get_logger("eval.runner")


DATASETS_DIR = Path(__file__).resolve().parent / "datasets"


class EvaluationRunner:
    """Runs one or more evaluation datasets end-to-end.

    Parameters
    ----------
    orchestrator:
        Pre-constructed retrieval orchestrator. If ``None`` a default one is
        built with ``Neo4jAdapter``. In tests, build it with an
        ``InMemoryGraphStore`` for isolation.
    generator:
        Pre-constructed grounded generator. Defaults to the registered
        provider (``stub`` locally).
    graph_store / object_store:
        If provided, the runner will bootstrap each dataset's ``corpus/``
        through the normal ingestion agents before answering its questions.
    """

    def __init__(
        self,
        *,
        orchestrator: RetrievalOrchestrator | None = None,
        generator: GroundedGenerator | None = None,
        graph_store: Any | None = None,
        object_store: ObjectStore | None = None,
    ) -> None:
        self.orch = orchestrator or RetrievalOrchestrator()
        self.gen = generator or GroundedGenerator()
        self.graph_store = graph_store
        self.object_store = object_store

    # ------------------------------------------------------------------
    # Dataset loading
    # ------------------------------------------------------------------

    def dataset_dir(self, name: str) -> Path:
        return DATASETS_DIR / name

    def available_datasets(self) -> list[str]:
        if not DATASETS_DIR.exists():
            return []
        return sorted(
            p.name for p in DATASETS_DIR.iterdir()
            if p.is_dir() and (p / "items.jsonl").exists()
        )

    # ------------------------------------------------------------------
    # Single dataset run
    # ------------------------------------------------------------------

    async def run_dataset(self, name: str) -> DatasetReport:
        ds_dir = self.dataset_dir(name)
        items_path = ds_dir / "items.jsonl"
        gold_path = ds_dir / "gold.jsonl"
        corpus_dir = ds_dir / "corpus"

        if not items_path.exists():
            raise FileNotFoundError(f"items.jsonl missing for dataset '{name}'")

        items = _load_jsonl(items_path)
        gold_list = _load_jsonl(gold_path) if gold_path.exists() else []
        gold_by_id = {str(g.get("id")): g for g in gold_list if "id" in g}

        # Bootstrap the corpus if a store was injected. This is idempotent
        # because of content-addressed SHAs. Import is deferred because
        # ``bootstrap`` pulls the ingest agents, which indirectly import the
        # runner when the ``eval_agent`` module is loaded.
        if self.graph_store is not None and self.object_store is not None and corpus_dir.exists():
            from .bootstrap import bootstrap_dataset

            matter_id = _matter_for_dataset(name)
            files = await bootstrap_dataset(
                corpus_dir=corpus_dir,
                object_store=self.object_store,
                graph_store=self.graph_store,
                matter_id=matter_id,
            )
            log.info("eval.bootstrap_done", dataset=name, files=files)

        results: list[ItemResult] = []
        for item in items:
            item_id = str(item.get("id") or f"item_{len(results)}")
            question = str(item.get("question", ""))
            matter_scope = item.get("matter_scope") or _matter_for_dataset(name)

            t0 = time.perf_counter()
            try:
                pack = await self.orch.answer(
                    question=question,
                    matter_scope=matter_scope,
                )
                answer = await self.gen.generate(pack, trace_id=f"eval-{item_id}")
                err: str | None = None
            except Exception as e:  # noqa: BLE001
                log.warning("eval.item_failed", id=item_id, error=str(e))
                err = str(e)
                pack = None
                answer = None
            latency = time.perf_counter() - t0

            gold = gold_by_id.get(item_id, {})
            results.append(
                _to_item_result(
                    item_id=item_id,
                    question=question,
                    matter_scope=matter_scope,
                    pack=pack,
                    answer=answer,
                    gold=gold,
                    latency=latency,
                    error=err,
                )
            )

        summary = _summarise(results)
        log.info("eval.dataset_done", dataset=name, **summary.model_dump())
        return DatasetReport(dataset=name, summary=summary, results=results)

    # ------------------------------------------------------------------
    # Multi-dataset run
    # ------------------------------------------------------------------

    async def run(
        self,
        datasets: list[str] | None = None,
    ) -> EvaluationReport:
        names = datasets or self.available_datasets()
        reports: list[DatasetReport] = []
        for name in names:
            reports.append(await self.run_dataset(name))
        provider = getattr(self.gen.provider, "name", "unknown")
        return EvaluationReport(
            datasets=reports,
            generated_at=dt.datetime.now(dt.UTC).isoformat(),
            provider=provider,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _matter_for_dataset(name: str) -> str | None:
    """Private-matter datasets are ingested under a deterministic matter id
    so the retrieval orchestrator scopes its BFS + Qdrant filter correctly."""
    if name.startswith("private_matter"):
        return f"eval_{name}"
    return None


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def _to_item_result(
    *,
    item_id: str,
    question: str,
    matter_scope: str | None,
    pack: Any,
    answer: Any,
    gold: dict[str, Any],
    latency: float,
    error: str | None,
) -> ItemResult:
    if answer is None or pack is None:
        return ItemResult(
            id=item_id,
            question=question,
            matter_scope=matter_scope,
            answer="",
            insufficient_evidence=True,
            confidence="low",
            citations=[],
            pack_spans=[],
            pack_tiers=[],
            pack_node_ids=[],
            gold=gold,
            latency_s=latency,
            notes=[f"error:{error}"] if error else [],
            extras={},
        )

    # Flatten pack markers + metadata for the metric functions.
    pack_spans = [s.marker.removeprefix("S") for s in pack.spans]
    pack_tiers = [int(s.tier) for s in pack.spans]
    pack_node_ids = [s.node_id for s in pack.spans]
    citations = [c.model_dump(mode="json") for c in answer.legal_basis] + [
        c.model_dump(mode="json") for c in answer.supporting_private_sources
    ]

    return ItemResult(
        id=item_id,
        question=question,
        matter_scope=matter_scope,
        answer=answer.answer,
        insufficient_evidence=answer.insufficient_evidence,
        confidence=answer.confidence,
        citations=citations,
        pack_spans=pack_spans,
        pack_tiers=pack_tiers,
        pack_node_ids=pack_node_ids,
        gold=gold,
        latency_s=latency,
        notes=list(answer.notes or []),
        extras=dict(answer.extras or {}),
    )


def _summarise(results_models: list[ItemResult]) -> EvaluationSummary:
    results = [r.model_dump() for r in results_models]
    lat = latency_stats(results)
    return EvaluationSummary(
        items=len(results),
        grounding_rate=grounding_rate(results),
        unsupported_claim_rate=unsupported_claim_rate(results),
        fabricated_marker_rate=fabricated_marker_rate(results),
        citation_faithfulness=citation_faithfulness(results),
        span_citation_correctness=span_citation_correctness(results),
        pack_utilisation=pack_utilisation(results),
        tier1_anchor_rate=tier1_anchor_rate(results),
        retrieval_hit_rate=retrieval_hit_rate(results),
        retrieval_coverage=retrieval_coverage(results),
        refusal_rate=refusal_rate(results),
        false_refusal_rate=false_refusal_rate(results),
        true_refusal_rate=true_refusal_rate(results),
        crosswalk_mapping_accuracy=crosswalk_mapping_accuracy(results),
        latency_mean_s=lat["mean"],
        latency_p50_s=lat["p50"],
        latency_p95_s=lat["p95"],
        latency_max_s=lat["max"],
    )
