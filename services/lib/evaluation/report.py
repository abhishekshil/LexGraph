"""Evaluation report models + threshold loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from ..core import settings


class ItemResult(BaseModel):
    """Per-item evaluation record. This is what runners dump to disk."""

    id: str
    question: str
    matter_scope: str | None = None
    answer: str
    insufficient_evidence: bool = False
    confidence: str = "low"
    citations: list[dict[str, Any]] = Field(default_factory=list)
    pack_spans: list[str] = Field(default_factory=list)
    pack_tiers: list[int] = Field(default_factory=list)
    pack_node_ids: list[str] = Field(default_factory=list)
    gold: dict[str, Any] = Field(default_factory=dict)
    latency_s: float = 0.0
    notes: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class EvaluationSummary(BaseModel):
    """Aggregated metrics across one dataset run."""

    items: int
    grounding_rate: float
    unsupported_claim_rate: float
    fabricated_marker_rate: float
    citation_faithfulness: float
    span_citation_correctness: float
    pack_utilisation: float
    tier1_anchor_rate: float
    retrieval_hit_rate: float
    retrieval_coverage: float
    refusal_rate: float
    false_refusal_rate: float
    true_refusal_rate: float
    crosswalk_mapping_accuracy: float
    latency_mean_s: float
    latency_p50_s: float
    latency_p95_s: float
    latency_max_s: float


class DatasetReport(BaseModel):
    dataset: str
    summary: EvaluationSummary
    results: list[ItemResult] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """A full run — one or more datasets."""

    datasets: list[DatasetReport] = Field(default_factory=list)
    generated_at: str = ""
    provider: str = "unknown"

    def to_json(self) -> str:
        return self.model_dump_json(indent=2)


# ---------------------------------------------------------------------------
# Threshold loading + gating
# ---------------------------------------------------------------------------


DEFAULT_THRESHOLDS_PATH = Path(settings.repo_root) / "configs" / "eval_thresholds.yaml"


class ThresholdViolation(BaseModel):
    dataset: str
    metric: str
    observed: float
    required: float
    kind: str  # "min" or "max"


def load_thresholds(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = path or DEFAULT_THRESHOLDS_PATH
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def check_thresholds(
    report: EvaluationReport,
    thresholds: dict[str, dict[str, Any]] | None = None,
) -> list[ThresholdViolation]:
    """Compare a report against a thresholds YAML and return violations.

    The YAML supports::

        <dataset_name>:
          min:
            grounding_rate: 0.8
            tier1_anchor_rate: 0.9
          max:
            fabricated_marker_rate: 0.02
            latency_p95_s: 5.0

        _default:
          min: {...}
          max: {...}
    """
    thresholds = thresholds or load_thresholds()
    if not thresholds:
        return []
    default = thresholds.get("_default") or {}
    violations: list[ThresholdViolation] = []
    for ds in report.datasets:
        spec = thresholds.get(ds.dataset) or {}
        # Merge default first, then dataset-specific. A ``null`` value in the
        # dataset-specific block removes that threshold entirely — this is how
        # datasets opt out of a default (e.g. private matters don't care
        # about tier-1 anchoring).
        mins = {**(default.get("min") or {}), **(spec.get("min") or {})}
        maxs = {**(default.get("max") or {}), **(spec.get("max") or {})}
        mins = {k: v for k, v in mins.items() if v is not None}
        maxs = {k: v for k, v in maxs.items() if v is not None}
        summary = ds.summary.model_dump()
        for metric, required in mins.items():
            if metric not in summary:
                continue
            observed = float(summary[metric])
            if observed + 1e-9 < float(required):
                violations.append(
                    ThresholdViolation(
                        dataset=ds.dataset,
                        metric=metric,
                        observed=observed,
                        required=float(required),
                        kind="min",
                    )
                )
        for metric, required in maxs.items():
            if metric not in summary:
                continue
            observed = float(summary[metric])
            if observed > float(required) + 1e-9:
                violations.append(
                    ThresholdViolation(
                        dataset=ds.dataset,
                        metric=metric,
                        observed=observed,
                        required=float(required),
                        kind="max",
                    )
                )
    return violations
