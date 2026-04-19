"""Citation-level metrics."""

from __future__ import annotations

import re
from typing import Any


_MARKER_NUM_RE = re.compile(r"\[S(\d+)\]")


def citation_faithfulness(results: list[dict[str, Any]]) -> float:
    """Fraction of ``[S#]`` tokens in the answer whose marker exists in the pack.

    Complement of :func:`fabricated_marker_rate` but counted once per marker
    occurrence, not per unique marker.
    """
    if not results:
        return 0.0
    total_refs = 0
    valid_refs = 0
    for r in results:
        pack = {str(m).removeprefix("S") if isinstance(m, str) else str(m)
                for m in r.get("pack_spans", [])}
        for m in _MARKER_NUM_RE.findall(r.get("answer", "")):
            total_refs += 1
            if m in pack:
                valid_refs += 1
    return valid_refs / total_refs if total_refs else 0.0


def span_citation_correctness(results: list[dict[str, Any]]) -> float:
    """Fraction of emitted citations that carry both ``excerpt`` and
    ``source_span_id`` — a structural-correctness proxy."""
    if not results:
        return 0.0
    total = 0
    ok = 0
    for r in results:
        for c in r.get("citations", []):
            total += 1
            if c.get("excerpt") and c.get("source_span_id"):
                ok += 1
    return ok / total if total else 0.0


def pack_utilisation(results: list[dict[str, Any]]) -> float:
    """Mean fraction of pack spans that were actually cited in the answer.

    Low utilisation means the pack is too bloated (token-budget waste);
    high utilisation (near 1.0) across the board means we may be under-packing.
    """
    if not results:
        return 0.0
    samples: list[float] = []
    for r in results:
        pack = [str(m).removeprefix("S") if isinstance(m, str) else str(m)
                for m in r.get("pack_spans", [])]
        if not pack:
            continue
        used = {m for m in _MARKER_NUM_RE.findall(r.get("answer", ""))}
        samples.append(len(used & set(pack)) / len(pack))
    return sum(samples) / len(samples) if samples else 0.0
