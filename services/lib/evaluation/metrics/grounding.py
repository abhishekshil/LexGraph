"""Grounding metrics.

``grounding_rate``  — fraction of claim-sentences in the final answer that
carry at least one ``[S#]`` marker.

``unsupported_claim_rate`` — complement of grounding rate.

``fabricated_marker_rate`` — fraction of ``[S#]`` markers that reference
spans **not** present in the pack (counted across the answer body).

Both use the same pragmatic sentence splitter as the answer enforcer so
scores match what the user sees.
"""

from __future__ import annotations

import re
from typing import Any


_MARKER_RE = re.compile(r"\[S\d+\]")
_MARKER_NUM_RE = re.compile(r"\[S(\d+)\]")


def grounding_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of claim-sentences with at least one [S#] marker."""
    if not results:
        return 0.0
    total = 0
    cited = 0
    for r in results:
        for sent in _claim_sentences(r.get("answer", "")):
            total += 1
            if _MARKER_RE.search(sent):
                cited += 1
    return cited / total if total else 0.0


def unsupported_claim_rate(results: list[dict[str, Any]]) -> float:
    return 1.0 - grounding_rate(results)


def fabricated_marker_rate(results: list[dict[str, Any]]) -> float:
    """Fraction of [S#] tokens in the answer that don't exist in the pack."""
    if not results:
        return 0.0
    total = 0
    bad = 0
    for r in results:
        pack = _pack_set(r.get("pack_spans", []))
        for m in _MARKER_NUM_RE.findall(r.get("answer", "")):
            total += 1
            if m not in pack:
                bad += 1
    return bad / total if total else 0.0


_HEADERS = (
    "answer:",
    "legal basis:",
    "confidence:",
    "insufficient evidence:",
    "conflicts:",
    "supporting private material:",
)


def _claim_sentences(answer: str) -> list[str]:
    # Strip the "Answer:" / "Legal basis:" etc. labels off the *line* that
    # carries them; otherwise a full paragraph glued to the label would be
    # dropped as a header.
    cleaned_lines: list[str] = []
    for line in (answer or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        low = stripped.lower()
        matched_header = next((h for h in _HEADERS if low.startswith(h)), None)
        if matched_header is not None:
            remainder = stripped[len(matched_header) :].strip()
            if remainder:
                cleaned_lines.append(remainder)
            continue
        cleaned_lines.append(stripped)
    body = " ".join(cleaned_lines)
    out: list[str] = []
    for sent in re.split(r"(?<=[\.\!\?])\s+", body):
        s = sent.strip()
        if not s or _is_header(s):
            continue
        out.append(s)
    return out


def _is_header(s: str) -> bool:
    low = s.lower().rstrip(":").strip()
    return low in (
        "answer",
        "legal basis",
        "confidence",
        "insufficient evidence",
        "conflicts",
        "supporting private material",
    ) or s.lower().startswith(
        (
            "answer:",
            "legal basis:",
            "confidence:",
            "insufficient evidence:",
            "conflicts:",
            "supporting private material:",
        )
    )


def _pack_set(pack_spans: list[str]) -> set[str]:
    s: set[str] = set()
    for m in pack_spans:
        if not isinstance(m, str):
            continue
        s.add(m.removeprefix("S") if m.startswith("S") else m)
    return s
