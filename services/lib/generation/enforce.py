"""Answer grounding enforcement.

The generator's output is untrusted text. This module is the *only* gate
between the model and the user. Its jobs:

  1. Parse the response into the six declared sections (Answer, Legal basis,
     Supporting private material, Conflicts, Confidence, Insufficient evidence).
  2. Drop every sentence whose citation markers aren't backed by the pack.
  3. Strip fabricated citations inside valid sentences.
  4. Normalise confidence labels.
  5. Emit a :class:`EnforcementReport` describing what was rejected.

The rules here are deliberately strict. If the model hallucinates, the user
sees the refusal path, not the hallucination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from ..core import get_logger
from ..data_models.evidence import EvidencePack


log = get_logger("generation.enforce")


_MARKER_RE = re.compile(r"\[S(\d+)\]")
_SECTION_HEADERS = (
    "answer:",
    "legal basis:",
    "supporting private material:",
    "conflicts:",
    "confidence:",
    "insufficient evidence:",
)
_CONFIDENCE_RE = re.compile(r"\bconfidence:\s*(high|medium|low)\b", re.IGNORECASE)
_INSUFFICIENT_RE = re.compile(r"\binsufficient evidence:\s*(yes|no)\b", re.IGNORECASE)


@dataclass
class EnforcedAnswer:
    """Structured, grounding-enforced view of the generator output."""

    answer: str
    legal_basis: list[str] = field(default_factory=list)
    private_material: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "low"
    insufficient: bool = True
    used_markers: set[str] = field(default_factory=set)


@dataclass
class EnforcementReport:
    dropped_sentences: list[str] = field(default_factory=list)
    fabricated_markers: set[str] = field(default_factory=set)
    total_sentences: int = 0
    kept_sentences: int = 0

    @property
    def rejection_rate(self) -> float:
        if self.total_sentences == 0:
            return 0.0
        return len(self.dropped_sentences) / self.total_sentences


def enforce(text: str, pack: EvidencePack) -> tuple[EnforcedAnswer, EnforcementReport]:
    """Validate ``text`` against ``pack``; return the cleaned answer + report."""
    allowed = {s.marker for s in pack.spans}
    sections = _split_sections(text)
    report = EnforcementReport()

    answer_text, used_in_answer = _filter_section(
        sections.get("answer", ""), allowed, report
    )

    legal_lines = _filter_bullets(sections.get("legal basis", ""), allowed, report)
    private_lines = _filter_bullets(
        sections.get("supporting private material", ""), allowed, report
    )
    conflict_lines = _filter_bullets(
        sections.get("conflicts", ""), allowed, report, require_citation=False
    )

    confidence = _parse_confidence(sections.get("confidence", "")) or "low"
    insufficient = _parse_insufficient(sections.get("insufficient evidence", ""))

    used: set[str] = set(used_in_answer)
    for line in legal_lines + private_lines:
        used.update(f"S{m}" for m in _MARKER_RE.findall(line))

    # Fall back to insufficient if we removed everything meaningful.
    if not answer_text.strip():
        insufficient = True
        confidence = "low"

    cleaned = EnforcedAnswer(
        answer=answer_text.strip(),
        legal_basis=legal_lines,
        private_material=private_lines,
        conflicts=conflict_lines,
        confidence=confidence,
        insufficient=insufficient,
        used_markers=used,
    )
    log.info(
        "generation.enforced",
        total=report.total_sentences,
        kept=report.kept_sentences,
        dropped=len(report.dropped_sentences),
        fabricated=len(report.fabricated_markers),
        confidence=confidence,
        insufficient=insufficient,
    )
    return cleaned, report


# ---------------------------------------------------------------------------
# Section parsing
# ---------------------------------------------------------------------------


def _split_sections(text: str) -> dict[str, str]:
    """Split the model output into its declared sections.

    The prompt asks the model for a fixed header ordering; this parser is
    tolerant: headers can appear with slight casing / spacing variations and
    any unknown content before the first header is treated as ``answer``.
    """
    lines = text.splitlines()
    buckets: dict[str, list[str]] = {h.rstrip(":"): [] for h in _SECTION_HEADERS}
    current = "answer"
    buckets.setdefault(current, [])
    for line in lines:
        stripped = line.strip()
        low = stripped.lower()
        matched = False
        for h in _SECTION_HEADERS:
            if low.startswith(h):
                current = h.rstrip(":")
                remainder = stripped[len(h) :].strip()
                if remainder:
                    buckets[current].append(remainder)
                matched = True
                break
        if not matched:
            buckets[current].append(line)
    return {k: "\n".join(v).strip() for k, v in buckets.items()}


# ---------------------------------------------------------------------------
# Sentence-level filtering
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> list[str]:
    """Pragmatic sentence splitter.

    A sentence ends at ``.``/``!``/``?`` optionally followed by one or more
    trailing citation markers (``[S3]``). The next sentence starts after
    whitespace. Markers glued to the preceding sentence's punctuation stay
    with that sentence, so grounding-check sees them.
    """
    text = text.strip()
    if not text:
        return []
    # Split where a sentence-ending punctuation (possibly followed by [S#]
    # markers) is followed by whitespace and then a capital/digit/marker/bullet.
    pattern = re.compile(
        r"(?<=[\.\!\?])(?:\s*\[S\d+\])*\s+(?=[A-Z0-9\-\*•\[])"
    )
    # We want to keep trailing markers glued to the preceding sentence, so do
    # a scan-based split instead of re.split (which would consume markers).
    out: list[str] = []
    start = 0
    for m in pattern.finditer(text):
        # The preceding sentence includes any markers that came right after
        # the period — find them and attach.
        end = m.start()
        # Walk forward past trailing markers & spaces that belong to the
        # preceding sentence.
        trailing = re.match(r"(?:\s*\[S\d+\])+", text[end:])
        if trailing:
            end += trailing.end()
        out.append(text[start:end].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def _filter_section(
    text: str, allowed: set[str], report: EnforcementReport
) -> tuple[str, list[str]]:
    kept: list[str] = []
    used: list[str] = []
    for sent in _split_sentences(text):
        report.total_sentences += 1
        markers_raw = _MARKER_RE.findall(sent)
        markers = {f"S{m}" for m in markers_raw}
        if not markers:
            # Claim without citation — drop.
            report.dropped_sentences.append(sent)
            continue
        fabricated = markers - allowed
        if fabricated:
            report.fabricated_markers.update(fabricated)
            # Strip fabricated markers; only keep the sentence if *some* valid
            # marker remains.
            cleaned_sent = sent
            for f in fabricated:
                cleaned_sent = cleaned_sent.replace(f"[{f}]", "")
            remaining = {f"S{m}" for m in _MARKER_RE.findall(cleaned_sent)}
            if not (remaining & allowed):
                report.dropped_sentences.append(sent)
                continue
            sent = re.sub(r"\s{2,}", " ", cleaned_sent).strip()
            markers = remaining

        kept.append(sent)
        used.extend(m for m in (markers & allowed))
        report.kept_sentences += 1
    return " ".join(kept), used


def _filter_bullets(
    text: str,
    allowed: set[str],
    report: EnforcementReport,
    *,
    require_citation: bool = True,
) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    kept: list[str] = []
    for raw in lines:
        line = raw.lstrip("-* •").strip()
        if not line:
            continue
        markers = {f"S{m}" for m in _MARKER_RE.findall(line)}
        if require_citation and not markers:
            report.dropped_sentences.append(line)
            continue
        fabricated = markers - allowed
        if fabricated:
            report.fabricated_markers.update(fabricated)
            for f in fabricated:
                line = line.replace(f"[{f}]", "")
            line = re.sub(r"\s{2,}", " ", line).strip()
            remaining = {f"S{m}" for m in _MARKER_RE.findall(line)}
            if require_citation and not (remaining & allowed):
                report.dropped_sentences.append(raw)
                continue
        if line:
            kept.append(line)
    return kept


def _parse_confidence(text: str) -> Literal["low", "medium", "high"] | None:
    m = _CONFIDENCE_RE.search(text)
    if not m:
        # Sometimes the model writes just the value on its own line.
        clean = text.strip().lower()
        if clean in {"high", "medium", "low"}:
            return clean  # type: ignore[return-value]
        return None
    return m.group(1).lower()  # type: ignore[return-value]


def _parse_insufficient(text: str) -> bool:
    m = _INSUFFICIENT_RE.search(text)
    if not m:
        return "yes" in text.strip().lower()
    return m.group(1).lower() == "yes"


def format_answer(clean: EnforcedAnswer) -> str:
    """Render the enforced answer back into the canonical 6-section layout.

    This is the string shown to users / stored in :attr:`Answer.answer`.
    """
    parts: list[str] = []
    parts.append("Answer:")
    parts.append(clean.answer or "No grounded answer could be produced.")
    if clean.legal_basis:
        parts.append("\nLegal basis:")
        parts.extend(f"- {ln}" for ln in clean.legal_basis)
    if clean.private_material:
        parts.append("\nSupporting private material:")
        parts.extend(f"- {ln}" for ln in clean.private_material)
    if clean.conflicts:
        parts.append("\nConflicts:")
        parts.extend(f"- {ln}" for ln in clean.conflicts)
    parts.append(f"\nConfidence: {clean.confidence.upper()}")
    parts.append(f"Insufficient evidence: {'YES' if clean.insufficient else 'NO'}")
    return "\n".join(parts)
