"""Refusal metrics.

``refusal_rate``       — fraction of items where the system produced a refusal
                         (``insufficient_evidence = True``).
``false_refusal_rate`` — fraction of *answerable* items (those with gold
                         expectations) that were refused anyway. High values
                         indicate retrieval holes.
``true_refusal_rate``  — fraction of *unanswerable* items (no gold) that
                         were correctly refused. High = system doesn't bluff.
"""

from __future__ import annotations

from typing import Any


def refusal_rate(results: list[dict[str, Any]]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if r.get("insufficient_evidence")) / len(results)


def false_refusal_rate(results: list[dict[str, Any]]) -> float:
    answerable = [r for r in results if _has_expectation(r.get("gold"))]
    if not answerable:
        return 0.0
    bad = sum(1 for r in answerable if r.get("insufficient_evidence"))
    return bad / len(answerable)


def true_refusal_rate(results: list[dict[str, Any]]) -> float:
    unanswerable = [r for r in results if not _has_expectation(r.get("gold"))]
    if not unanswerable:
        return 0.0
    ok = sum(1 for r in unanswerable if r.get("insufficient_evidence"))
    return ok / len(unanswerable)


def _has_expectation(gold: dict[str, Any] | None) -> bool:
    if not gold:
        return False
    keys = ("expected_mapping", "expected_sections", "expected_node_ids", "expected_tier1")
    return any(gold.get(k) for k in keys)
