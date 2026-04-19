"""Crosswalk mapping accuracy (IPC↔BNS / CrPC↔BNSS / IEA↔BSA)."""

from __future__ import annotations

from typing import Any


def crosswalk_mapping_accuracy(results: list[dict[str, Any]]) -> float:
    """Each item's gold may include a 'expected_mapping' {source, target}.

    Hit if any citation in the answer references the expected target section.
    """
    if not results:
        return 0.0
    total = 0
    ok = 0
    for r in results:
        gold = r.get("gold") or {}
        expected = gold.get("expected_mapping")
        if not expected:
            continue
        total += 1
        target = str(expected.get("target", "")).lower()
        for c in r.get("citations", []):
            label = (c.get("section_or_paragraph") or "").lower()
            if target and target in label:
                ok += 1
                break
    return ok / total if total else 0.0
