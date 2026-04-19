"""Citation extractor for Indian legal text.

Rule-based but structurally rich: every match is resolved to a
``canonical_id`` following the schema documented in :mod:`citation_patterns`.
The graph writer uses that id to ``MERGE`` a :class:`Case` node so that two
writers citing the same case with different reporter formats converge onto
one node.

The extractor is deliberately **conservative**: it prefers a longer, more
informative match over a shorter one (so a case title followed immediately
by a reporter citation becomes a single enriched :class:`Citation`, not two
overlapping ones). It also discards matches whose numeric components look
implausible (year outside [1800, current+1], volume or page == 0, etc.).
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from .citation_patterns import (
    AIR_RE,
    CASE_TITLE_RE,
    CRILJ_RE,
    HC_NEUTRAL_RE,
    ILR_RE,
    INSC_RE,
    MANU_RE,
    SCC_ONLINE_RE,
    SCC_RE,
    SCR_RE,
    normalise_court_code,
)


# Maximum plausible year for a reported judgment; anything beyond next year is
# almost certainly a volume number accidentally picked up as a year.
_MAX_YEAR = datetime.now(timezone.utc).year + 1
_MIN_YEAR = 1800

# How close (in characters) two adjacent matches need to be for merging the
# case title with a trailing reporter citation. Gaps larger than this look
# like separate citations on different lines.
_MERGE_GAP = 40


@dataclass
class Citation:
    """Structured citation extracted from free text.

    Attributes
    ----------
    raw:
        Exact substring as it appeared in the source text.
    kind:
        One of ``"neutral" | "reporter" | "case_title" | "combined"``.
        ``combined`` means a case title fused with a trailing reporter
        citation (the most useful kind downstream).
    start, end:
        Character offsets into the originating text.
    canonical_id:
        Deterministic id used to collapse the same case across different
        reporters / formatting; see :mod:`citation_patterns` for the schema.
    court:
        Canonical court token (e.g. ``'sc'``, ``'del'``) or ``'unknown'``.
    year:
        Four-digit year of the citation, if known.
    reporter:
        Reporter code: ``'insc' | 'scc' | 'scr' | 'air' | 'scc_online' |
        'manu' | 'ilr' | 'crilj' | 'neutral' | None``.
    volume / page / seq:
        Reporter-specific numeric components; populated best-effort.
    parties:
        Tuple ``(petitioner, respondent)`` if the match was a case title.
    """

    raw: str
    kind: str
    start: int
    end: int
    canonical_id: str
    court: str = "unknown"
    year: int | None = None
    reporter: str | None = None
    volume: str | None = None
    page: str | None = None
    seq: str | None = None
    parties: tuple[str, str] | None = None
    extras: dict[str, str] = field(default_factory=dict)

    # Convenience used by the graph writer.
    @property
    def target_node_type(self) -> str:
        return "Case"


# ---------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------

class CitationExtractor:
    """Stateless extractor. Instances are cheap; reuse across calls."""

    def extract(self, text: str) -> list[Citation]:
        out: list[Citation] = []

        out.extend(_from_insc(text))
        out.extend(_from_hc_neutral(text))
        out.extend(_from_scc(text))
        out.extend(_from_scr(text))
        out.extend(_from_scc_online(text))
        out.extend(_from_air(text))
        out.extend(_from_manu(text))
        out.extend(_from_ilr(text))
        out.extend(_from_crilj(text))

        titles = list(_from_case_title(text))

        # Prefer to merge a case title with an adjacent reporter citation into
        # one "combined" record. This is what downstream code really wants:
        # a human-readable title *and* a stable canonical id.
        reporter_cits = list(out)
        out = _merge_titles(titles, reporter_cits, text)

        return _dedupe(out)


def extract_citations(text: str) -> list[Citation]:
    return CitationExtractor().extract(text)


# ---------------------------------------------------------------------------
# Per-pattern extractors
# ---------------------------------------------------------------------------

def _from_insc(text: str) -> Iterable[Citation]:
    for m in INSC_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        seq = m.group("seq")
        yield Citation(
            raw=m.group(0),
            kind="neutral",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:sc:insc:{year}:{seq}",
            court="sc",
            year=year,
            reporter="insc",
            seq=seq,
        )


def _from_hc_neutral(text: str) -> Iterable[Citation]:
    for m in HC_NEUTRAL_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        court = normalise_court_code(m.group("court"))
        if court == "unknown":
            # Noise guard: the regex is loose, reject obvious false positives.
            continue
        seq = m.group("seq")
        yield Citation(
            raw=m.group(0),
            kind="neutral",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:{court}:neutral:{year}:{seq}",
            court=court,
            year=year,
            reporter="neutral",
            seq=seq,
            extras={"hc_code": m.group("court")},
        )


_SCC_SUB_MAP: dict[str, str] = {
    "cri": "cri",
    "civ": "civ",
    "l&s": "ls",
}


def _from_scc(text: str) -> Iterable[Citation]:
    for m in SCC_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        vol = m.group("vol")
        page = m.group("page")
        sub_raw = (m.group("sub") or "").strip().lower()
        sub = _SCC_SUB_MAP.get(sub_raw, sub_raw)
        reporter = f"scc_{sub}" if sub else "scc"
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:sc:{reporter}:{year}:{vol}:{page}",
            court="sc",
            year=year,
            reporter=reporter,
            volume=vol,
            page=page,
        )


def _from_scr(text: str) -> Iterable[Citation]:
    for m in SCR_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        vol = m.group("vol")
        page = m.group("page")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:sc:scr:{year}:{vol}:{page}",
            court="sc",
            year=year,
            reporter="scr",
            volume=vol,
            page=page,
        )


def _from_scc_online(text: str) -> Iterable[Citation]:
    for m in SCC_ONLINE_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        court = normalise_court_code(m.group("court"))
        seq = m.group("seq")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:{court}:scc_online:{year}:{seq}",
            court=court,
            year=year,
            reporter="scc_online",
            seq=seq,
        )


def _from_air(text: str) -> Iterable[Citation]:
    for m in AIR_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        court = normalise_court_code(m.group("court"))
        page = m.group("page")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:{court}:air:{year}:{page}",
            court=court,
            year=year,
            reporter="air",
            page=page,
        )


def _from_manu(text: str) -> Iterable[Citation]:
    for m in MANU_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        court = normalise_court_code(m.group("court"))
        seq = m.group("seq")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:{court}:manu:{seq}:{year}",
            court=court,
            year=year,
            reporter="manu",
            seq=seq,
            extras={"manu_court_code": m.group("court").upper()},
        )


def _from_ilr(text: str) -> Iterable[Citation]:
    for m in ILR_RE.finditer(text):
        year = _year_or_none(m.group("year1") or m.group("year2"))
        if year is None:
            continue
        court = normalise_court_code(m.group("court"))
        page = m.group("page")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            canonical_id=f"case:{court}:ilr:{year}:{page}",
            court=court,
            year=year,
            reporter="ilr",
            page=page,
        )


def _from_crilj(text: str) -> Iterable[Citation]:
    for m in CRILJ_RE.finditer(text):
        year = _year_or_none(m.group("year"))
        if year is None:
            continue
        page = m.group("page")
        yield Citation(
            raw=m.group(0),
            kind="reporter",
            start=m.start(),
            end=m.end(),
            # CriLJ does not encode the court; tag as unknown.
            canonical_id=f"case:unknown:crilj:{year}:{page}",
            court="unknown",
            year=year,
            reporter="crilj",
            page=page,
        )


def _from_case_title(text: str) -> Iterable[Citation]:
    for m in CASE_TITLE_RE.finditer(text):
        p1_raw = m.group("p1").strip()
        p2_raw = m.group("p2").strip()
        p1, p1_shift = _strip_leading_noise(p1_raw)
        p2, _ = _strip_leading_noise(p2_raw)
        if not _looks_like_party(p1) or not _looks_like_party(p2):
            continue
        start = m.start() + p1_shift
        end = m.end()
        slug = _slug(f"{p1} v {p2}")
        yield Citation(
            raw=text[start:end],
            kind="case_title",
            start=start,
            end=end,
            canonical_id=f"case:title:{slug}",
            parties=(p1, p2),
        )


# ---------------------------------------------------------------------------
# Merging and deduplication
# ---------------------------------------------------------------------------

def _merge_titles(
    titles: list[Citation],
    reporters: list[Citation],
    text: str,
) -> list[Citation]:
    """Fuse each case title with its trailing reporter citation, if any.

    A title is fused with the *first* reporter citation whose ``start`` lies
    within :data:`_MERGE_GAP` characters after the title's ``end`` and whose
    canonical court is the same (or unknown). The combined record inherits
    the reporter's ``canonical_id`` (which is stable and precise) and the
    title's ``parties``.
    """
    merged: list[Citation] = []
    consumed_reporters: set[int] = set()

    for t in titles:
        candidate_idx: int | None = None
        best_gap = _MERGE_GAP + 1
        for i, r in enumerate(reporters):
            if i in consumed_reporters:
                continue
            gap = r.start - t.end
            # allow a small overlap (comma + space before the citation)
            if -2 <= gap < best_gap:
                candidate_idx = i
                best_gap = gap
        if candidate_idx is not None:
            r = reporters[candidate_idx]
            consumed_reporters.add(candidate_idx)
            start = t.start
            end = max(t.end, r.end)
            merged.append(
                Citation(
                    raw=text[start:end],
                    kind="combined",
                    start=start,
                    end=end,
                    canonical_id=r.canonical_id,
                    court=r.court,
                    year=r.year,
                    reporter=r.reporter,
                    volume=r.volume,
                    page=r.page,
                    seq=r.seq,
                    parties=t.parties,
                    extras=dict(r.extras),
                )
            )
        else:
            merged.append(t)

    # Reporter-only citations that weren't consumed by any title.
    for i, r in enumerate(reporters):
        if i not in consumed_reporters:
            merged.append(r)

    return merged


def _dedupe(items: list[Citation]) -> list[Citation]:
    """Remove overlapping / duplicate matches, preferring the longer one.

    When two matches overlap we keep the one that covers more characters; on
    ties we prefer the richer kind (``combined`` > ``reporter`` > ``neutral``
    > ``case_title``).
    """
    kind_rank = {"combined": 3, "reporter": 2, "neutral": 2, "case_title": 1}
    sorted_items = sorted(
        items,
        key=lambda c: (c.start, -(c.end - c.start), -kind_rank.get(c.kind, 0)),
    )
    out: list[Citation] = []
    for c in sorted_items:
        if out and c.start < out[-1].end:
            prev = out[-1]
            if (c.end - c.start) > (prev.end - prev.start) or (
                (c.end - c.start) == (prev.end - prev.start)
                and kind_rank.get(c.kind, 0) > kind_rank.get(prev.kind, 0)
            ):
                out[-1] = c
            continue
        out.append(c)
    return out


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _year_or_none(raw: str | None) -> int | None:
    if raw is None:
        return None
    try:
        y = int(raw)
    except ValueError:
        return None
    if _MIN_YEAR <= y <= _MAX_YEAR:
        return y
    return None


# Leading sentence words that commonly precede a case title in legal prose.
# When the regex accidentally folds one of these into p1 (or p2) we strip it
# off so the resulting ``parties`` tuple is clean.
_LEADING_NOISE: set[str] = {
    "see", "seeing", "cf", "cf.", "the", "this", "that", "in", "as", "per",
    "also", "even", "and", "but", "now", "here", "thus", "hence", "where",
    "when", "if", "following", "relying", "on", "reported", "citing",
}

# Tokens which, on their own, are never a party name — typically sentence
# verbs or fragments that the regex can attach to p2 before the real name.
_PARTY_STOPWORDS: set[str] = {
    "see", "the", "this", "that", "now", "here", "thus", "hence", "and",
    "but", "if", "or",
}


def _strip_leading_noise(s: str) -> tuple[str, int]:
    """Return ``(cleaned, shift)`` where ``shift`` is the number of characters
    removed from the left. Used to realign start offsets after stripping."""
    tokens = s.split()
    shift = 0
    while tokens and tokens[0].lower().rstrip(".,;:") in _LEADING_NOISE:
        # +1 for the whitespace that follows the noise token
        shift += len(tokens[0]) + 1
        tokens.pop(0)
    return " ".join(tokens), shift


def _looks_like_party(s: str) -> bool:
    """Reject matches that are clearly sentence fragments rather than party names.

    Accepts:
      * multi-token names (``"State of Rajasthan"``, ``"Ram Singh"``)
      * single-token names with >=3 chars that start with a capital letter
        and aren't common sentence stopwords (``"Vishaka"``, ``"Puttaswamy"``)
    Rejects single tokens that are stopwords or all-lowercase fragments.
    """
    tokens = s.split()
    if not tokens:
        return False
    first = tokens[0].rstrip(".,;:")
    lowered = first.lower()
    if lowered in _PARTY_STOPWORDS:
        return False
    if len(tokens) >= 2:
        return True
    # Single-token party must be ≥3 chars and start with a capital letter.
    return len(first) >= 3 and first[0].isupper()


def _slug(s: str) -> str:
    return _re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "unknown"


__all__ = ["Citation", "CitationExtractor", "extract_citations"]
