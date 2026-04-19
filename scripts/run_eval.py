"""CI regression gate for the evaluation suite.

Usage::

    python -m scripts.run_eval                          # all datasets
    python -m scripts.run_eval --datasets offence_ingredients_ipc_bns
    python -m scripts.run_eval --out data/eval/report.json
    python -m scripts.run_eval --no-gate                # don't fail on threshold breach

Behaviour:

* Builds an ephemeral in-memory graph + object store for the run so the gate
  is reproducible without a live Neo4j / MinIO.
* Writes a JSON report to ``data/eval/<ts>.json`` by default (or ``--out``).
* Loads thresholds from ``configs/eval_thresholds.yaml`` and compares every
  metric. Any violation prints a table and exits non-zero — which is what
  a CI job wires into the pipeline.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
from pathlib import Path

from services.lib.core import settings
from services.lib.evaluation import (
    EvaluationRunner,
    check_thresholds,
    load_thresholds,
)
from services.lib.generation import GroundedGenerator, StubProvider
from services.lib.graph import InMemoryGraphStore
from services.lib.retrieval.orchestrator import RetrievalOrchestrator
from services.lib.storage import get_object_store


def _default_out() -> Path:
    ts = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path(settings.repo_root) / "data" / "eval" / f"{ts}.json"


def _print_summary(report) -> None:
    print("\n=== Evaluation summary ===")
    print(f"provider: {report.provider}  generated_at: {report.generated_at}")
    for ds in report.datasets:
        s = ds.summary
        print(
            f"\n[{ds.dataset}] items={s.items}  "
            f"ground={s.grounding_rate:.2f} cit={s.citation_faithfulness:.2f} "
            f"fab={s.fabricated_marker_rate:.3f} tier1={s.tier1_anchor_rate:.2f} "
            f"hit={s.retrieval_hit_rate:.2f} cov={s.retrieval_coverage:.2f} "
            f"refuse={s.refusal_rate:.2f} falseref={s.false_refusal_rate:.2f} "
            f"cw={s.crosswalk_mapping_accuracy:.2f} "
            f"p95={s.latency_p95_s:.2f}s"
        )


def _print_violations(violations) -> None:
    print("\n!!! Threshold violations detected !!!\n")
    print(f"{'dataset':<32} {'metric':<32} {'kind':<4} {'observed':>10} {'required':>10}")
    print("-" * 92)
    for v in violations:
        print(
            f"{v.dataset:<32} {v.metric:<32} {v.kind:<4} "
            f"{v.observed:>10.4f} {v.required:>10.4f}"
        )


async def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--datasets", nargs="*", default=None,
                        help="Subset of datasets to run (default: all).")
    parser.add_argument("--out", type=Path, default=None,
                        help="Write full JSON report to this path.")
    parser.add_argument("--thresholds", type=Path, default=None,
                        help="Override thresholds YAML path.")
    parser.add_argument("--no-gate", action="store_true",
                        help="Skip threshold comparison (report-only mode).")
    parser.add_argument("--backend", choices=("memory", "neo4j"), default="memory",
                        help="Graph backend for the run.")
    args = parser.parse_args()

    # Force the deterministic stub provider so CI is reproducible. Developers
    # can run with OPENAI_API_KEY to try a real model locally.
    generator = GroundedGenerator(provider=StubProvider())

    if args.backend == "memory":
        # Force the local-disk object store so the script runs without MinIO.
        settings.minio_endpoint = ""
        graph_store = InMemoryGraphStore()
        orch = RetrievalOrchestrator(store=graph_store)
        get_object_store.cache_clear()
        object_store = get_object_store()
        runner = EvaluationRunner(
            orchestrator=orch,
            generator=generator,
            graph_store=graph_store,
            object_store=object_store,
        )
    else:
        runner = EvaluationRunner(generator=generator)

    report = await runner.run(datasets=args.datasets)

    out_path = args.out or _default_out()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report.to_json(), encoding="utf-8")
    print(f"wrote {out_path}")

    _print_summary(report)

    if args.no_gate:
        return 0

    thresholds = load_thresholds(args.thresholds) if args.thresholds else load_thresholds()
    if not thresholds:
        print("\n(no thresholds configured, skipping gate)")
        return 0

    violations = check_thresholds(report, thresholds)
    if violations:
        _print_violations(violations)
        return 2
    print("\nAll metrics meet thresholds. Gate: PASS")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(asyncio.run(_main()))
