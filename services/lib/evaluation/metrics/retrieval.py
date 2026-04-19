"""Retrieval-side evaluation metrics.

These operate on the ``pack_spans`` / ``pack_tiers`` / ``expected`` payloads
attached to each evaluation result. They do **not** look at the generator
output — they measure how well the retrieval layer put authoritative
material into the evidence pack in the first place.
"""

from __future__ import annotations

from typing import Any


def tier1_anchor_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of items whose evidence pack contains at least one tier-1 span."""
    if not results:
        return 0.0
    ok = 0
    for r in results:
        if any(int(t) == 1 for t in r.get("pack_tiers", [])):
            ok += 1
    return ok / len(results)


def retrieval_hit_rate(results: list[dict[str, Any]]) -> float:
    """Gold items may carry ``expected_section`` / ``expected_node_ids``.

    Item is a hit if any retrieved node / citation matches one of those.
    Items without expectations are skipped.
    """
    total = 0
    hits = 0
    for r in results:
        gold = r.get("gold") or {}
        expected_nodes = {
            _norm(n) for n in (gold.get("expected_node_ids") or [])
        }
        expected_sections = {
            _norm(s) for s in (gold.get("expected_sections") or [])
        }
        if not expected_nodes and not expected_sections:
            continue
        total += 1
        got = False
        for nid in r.get("pack_node_ids", []):
            if _norm(nid) in expected_nodes:
                got = True
                break
        if not got:
            for cit in r.get("citations", []):
                label = _norm(cit.get("section_or_paragraph") or "")
                if any(es in label or label in es for es in expected_sections if es):
                    got = True
                    break
        if got:
            hits += 1
    return hits / total if total else 0.0


def retrieval_coverage(results: list[dict[str, Any]]) -> float:
    """Fraction of items whose evidence pack was non-empty."""
    if not results:
        return 0.0
    ok = sum(1 for r in results if r.get("pack_spans"))
    return ok / len(results)


def _norm(s: str) -> str:
    return (s or "").strip().lower().replace(" ", "").replace(".", "")
