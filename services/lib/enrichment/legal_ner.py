"""Legal NER.

The regex + list layer is the *baseline* — it is cheap, offline, and
guaranteed to run. Optionally, a pluggable transformer model (see
:mod:`transformer_ner`) layers on top to recover entities the rules miss
(e.g. precedent titles embedded mid-sentence, judge names without a title,
multi-word organisations).

Output from both layers is merged and de-duplicated by span. When the same
text span is tagged by both sources the transformer label wins *only* if
the regex produced nothing at that offset — regex wins on ties because it
is the layer we control end-to-end.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Protocol


COURT_HINTS: dict[str, str] = {
    "Supreme Court of India": "SC",
    "Supreme Court": "SC",
    "High Court of Delhi": "HC",
    "Delhi High Court": "HC",
    "Bombay High Court": "HC",
    "Madras High Court": "HC",
    "Calcutta High Court": "HC",
    "Karnataka High Court": "HC",
    "Kerala High Court": "HC",
    "Allahabad High Court": "HC",
    "Gujarat High Court": "HC",
    "Punjab and Haryana High Court": "HC",
    "NCLAT": "TRIBUNAL",
    "NGT": "TRIBUNAL",
    "ITAT": "TRIBUNAL",
    "CAT": "TRIBUNAL",
    "NCDRC": "TRIBUNAL",
}

DATE_RE = re.compile(
    r"\b(\d{1,2})[\s\-/](?:(\d{1,2})|([A-Za-z]{3,9}))[\s\-/](\d{2,4})\b"
)

JUDGE_RE = re.compile(
    r"(?:Hon'ble\s+)?(?:Mr\.|Mrs\.|Ms\.|Dr\.|Justice|J\.)[\s.]*"
    r"(?P<name>[A-Z][A-Za-z\.\-']+(?:\s+[A-Z][A-Za-z\.\-']+){1,3})"
)

# Match "Party1 v. Party2" without relying on a trailing delimiter, so titles
# embedded in running prose ("Vishaka v. State of Rajasthan continues to
# govern...") are still picked up. We cap each side at 6 capitalised tokens
# (with optional "of" / "and") to avoid running off into the next sentence.
PARTY_V_RE = re.compile(
    r"(?P<p1>(?:[A-Z][A-Za-z\.\-']+)(?:\s+(?:of|and)\s+[A-Z][A-Za-z\.\-']+|\s+[A-Z][A-Za-z\.\-']+){0,5})"
    r"\s+v(?:s)?\.?\s+"
    r"(?P<p2>(?:[A-Z][A-Za-z\.\-']+)(?:\s+(?:of|and)\s+[A-Z][A-Za-z\.\-']+|\s+[A-Z][A-Za-z\.\-']+){0,5})"
)


@dataclass
class Entity:
    type: str
    text: str
    start: int
    end: int
    extra: dict[str, str] = field(default_factory=dict)


class _NERBackend(Protocol):
    """Protocol satisfied by any NER layer that returns :class:`Entity`."""

    def extract(self, text: str) -> list[Entity]: ...


class LegalNER:
    """Combined regex + optional transformer NER.

    Parameters
    ----------
    transformer:
        Optional secondary backend (see :class:`~services.lib.enrichment
        .transformer_ner.TransformerLegalNER`). When omitted the extractor is
        purely regex-based, which keeps tests and CI offline.
    """

    def __init__(self, transformer: _NERBackend | None = None) -> None:
        self._transformer = transformer

    def extract(self, text: str) -> list[Entity]:
        out: list[Entity] = list(self._extract_regex(text))
        if self._transformer is not None:
            # Transformer failures are swallowed by the wrapper itself so that
            # regex remains the guaranteed baseline.
            extra = self._transformer.extract(text)
            out.extend(extra)
        return _merge(out)

    # ------------------------------------------------------------------
    # Regex layer — stable, offline.
    # ------------------------------------------------------------------

    def _extract_regex(self, text: str) -> Iterable[Entity]:
        for name, level in COURT_HINTS.items():
            for m in re.finditer(re.escape(name), text, flags=re.IGNORECASE):
                yield Entity(
                    type="Court",
                    text=m.group(0),
                    start=m.start(),
                    end=m.end(),
                    extra={"level": level, "source": "regex"},
                )
        for m in JUDGE_RE.finditer(text):
            yield Entity(
                type="Judge",
                text=m.group("name"),
                start=m.start("name"),
                end=m.end("name"),
                extra={"source": "regex"},
            )
        for m in PARTY_V_RE.finditer(text):
            yield Entity(
                type="Party",
                text=m.group("p1").strip(),
                start=m.start("p1"),
                end=m.end("p1"),
                extra={"role": "petitioner", "source": "regex"},
            )
            yield Entity(
                type="Party",
                text=m.group("p2").strip(),
                start=m.start("p2"),
                end=m.end("p2"),
                extra={"role": "respondent", "source": "regex"},
            )
        for m in DATE_RE.finditer(text):
            yield Entity(
                type="Date",
                text=m.group(0),
                start=m.start(),
                end=m.end(),
                extra={"source": "regex"},
            )


def _merge(items: list[Entity]) -> list[Entity]:
    """Merge overlapping entities; regex wins on exact-span collisions.

    Two entities overlap when their character ranges intersect. We keep the
    *longer* span; on ties the regex-sourced entity wins because the regex
    layer is fully tested and deterministic.
    """
    def priority(e: Entity) -> int:
        return 1 if e.extra.get("source") == "regex" else 0

    sorted_items = sorted(
        items,
        key=lambda e: (e.start, -(e.end - e.start), -priority(e)),
    )
    out: list[Entity] = []
    for e in sorted_items:
        if out and e.start < out[-1].end:
            prev = out[-1]
            if (e.end - e.start) > (prev.end - prev.start):
                out[-1] = e
            # Equal-length + regex-tied overlap: keep the earlier (regex) entry.
            continue
        out.append(e)
    return out


__all__ = ["Entity", "LegalNER"]
