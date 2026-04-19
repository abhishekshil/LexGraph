"""Latency aggregation helpers."""

from __future__ import annotations

import statistics
from typing import Any


def latency_stats(results: list[dict[str, Any]]) -> dict[str, float]:
    samples = [float(r["latency_s"]) for r in results if "latency_s" in r]
    if not samples:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "max": 0.0}
    samples.sort()
    return {
        "mean": statistics.fmean(samples),
        "p50": _percentile(samples, 0.50),
        "p95": _percentile(samples, 0.95),
        "max": samples[-1],
    }


def _percentile(sorted_samples: list[float], pct: float) -> float:
    if not sorted_samples:
        return 0.0
    k = max(0, min(len(sorted_samples) - 1, int(round(pct * (len(sorted_samples) - 1)))))
    return sorted_samples[k]
