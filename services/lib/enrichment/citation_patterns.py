"""Pattern catalogue for Indian legal citations.

Centralises the regexes and lookup tables used by :mod:`citation_extractor`.
Keeping them here lets the graph-writer, reranker, and evaluation code share
the *same* normalisation ids without re-implementing the court code map.

Every pattern is anchored by a named ``kind`` which the extractor uses both
to tag the :class:`Citation` and to select a ``canonical_id`` template.

Canonical id schema (all lowercase, ``:`` separated, no whitespace):

* ``case:sc:insc:<year>:<seq>``            - neutral SC citation
* ``case:<court>:neutral:<year>:<seq>``    - HC neutral citation (e.g. 2023:DHC:1234)
* ``case:sc:scc:<year>:<vol>:<page>``      - Supreme Court Cases (main + sub-series)
* ``case:sc:scr:<year>:<vol>:<page>``      - Supreme Court Reports (official)
* ``case:sc:air:<year>:<page>``            - AIR (Supreme Court)
* ``case:<court>:air:<year>:<page>``       - AIR (High Court)
* ``case:<court>:scc_online:<year>:<seq>`` - SCC OnLine
* ``case:<court>:manu:<seq>:<year>``       - Manupatra
* ``case:<court>:ilr:<year>:<page>``       - Indian Law Reports
* ``case:unknown:crilj:<year>:<page>``     - Criminal Law Journal (reporter does not encode court)
* ``case:title:<slug>``                    - case-title only, no reporter citation found

The ``<court>`` token is the short code from :data:`COURT_CODE_TO_ID` (e.g.
``sc``, ``del``, ``bom``, ``mad``). ``<seq>`` is the serial number emitted by
the reporter / registry; ``<vol>`` and ``<page>`` are the volume and first
page. The schema is stable across reporters so that the graph writer can
confidently ``MERGE (c:Case {canonical_id: ...})`` when the same case is
cited by different reporters in different documents.
"""

from __future__ import annotations

import regex as re


# ---------------------------------------------------------------------------
# Court codes
# ---------------------------------------------------------------------------
# Canonical court ids. Keys include every variant we have seen in the wild
# (full name, reporter short code, SCC OnLine code, AIR code, MANU code).
# The value is the canonical token used inside ``canonical_id``. Keep this
# table conservative: only add a mapping when you are confident the code
# unambiguously identifies one court.

COURT_CODE_TO_ID: dict[str, str] = {
    # Supreme Court
    "sc": "sc",
    "supreme": "sc",
    "supreme court": "sc",
    "supreme court of india": "sc",
    "insc": "sc",
    # High Courts (reporter / SCC OnLine codes)
    "del": "del", "delhi": "del", "dhc": "del",
    "bom": "bom", "bombay": "bom", "bhc": "bom", "bhc-as": "bom",
    "mad": "mad", "madras": "mad", "mhc": "mad",
    "cal": "cal", "calcutta": "cal", "chc": "cal",
    "kar": "kar", "karnataka": "kar", "khc": "kar",
    "ker": "ker", "kerala": "ker", "kehc": "ker",
    "all": "all", "allahabad": "all", "ahc": "all",
    "ap": "ap", "andhra": "ap",
    "tel": "tel", "telangana": "tel", "ts": "tel",
    "guj": "guj", "gujarat": "guj",
    "hp": "hp",
    "j&k": "jk", "jk": "jk", "jammu": "jk",
    "jhar": "jhar", "jharkhand": "jhar",
    "mp": "mp", "madhya pradesh": "mp",
    "mani": "mani", "manipur": "mani",
    "megh": "megh", "meghalaya": "megh",
    "ori": "ori", "orissa": "ori", "odisha": "ori",
    "p&h": "ph", "ph": "ph", "punjab": "ph", "haryana": "ph",
    "pat": "pat", "patna": "pat",
    "raj": "raj", "rajasthan": "raj",
    "sik": "sik", "sikkim": "sik",
    "tri": "tri", "tripura": "tri",
    "utr": "utr", "uttarakhand": "utr", "utk": "utr",
    "chh": "chh", "chhattisgarh": "chh",
    "gau": "gau", "gauhati": "gau", "guw": "gau",
    # Tribunals — kept for completeness, do not appear in all reporters.
    "nclat": "nclat",
    "ngt": "ngt",
    "itat": "itat",
    "cat": "cat",
    # MANU-specific court codes differ: MANU/DE = Delhi, MANU/MH = Bombay,
    # MANU/KA = Karnataka, MANU/TN = Madras, MANU/WB = Calcutta, etc.
    "de": "del",
    "mh": "bom",
    "ka": "kar",
    "tn": "mad",
    "wb": "cal",
    "up": "all",
    "kl": "ker",
    "gj": "guj",
    "rh": "raj",
    "or": "ori",
    "ph_": "ph",
    "bh": "pat",
    "hp_": "hp",
    "jk_": "jk",
    "jh": "jhar",
    "uc": "utr",
    "cg": "chh",
    "as": "gau",
}


# ---------------------------------------------------------------------------
# Reporter citation patterns
# ---------------------------------------------------------------------------
# Each pattern uses named groups so the extractor can assemble a canonical id
# without re-parsing. ``kind`` is the category attached to the resulting
# :class:`Citation`.
#
# The ``court_re`` fragment accepts any of the court codes in
# :data:`COURT_CODE_TO_ID` (case-insensitively). It is defined below after
# that table.


def _court_alt(extra: tuple[str, ...] = ()) -> str:
    """Regex alternation of known court codes plus any extras."""
    codes = set(COURT_CODE_TO_ID.keys()) | set(extra)
    # Longer strings first so 'supreme court of india' wins over 'supreme'.
    sorted_codes = sorted(codes, key=len, reverse=True)
    escaped = [re.escape(c) for c in sorted_codes]
    return r"(?:" + "|".join(escaped) + r")"


_COURT_ALT = _court_alt()


# Neutral SC citation: "2023 INSC 845"
INSC_RE = re.compile(
    r"\b(?P<year>\d{4})\s+INSC\s+(?P<seq>\d{1,6})\b",
    re.IGNORECASE,
)

# Neutral HC citation: "2023:DHC:1234", "2022:BHC-AS:1234",
# "2023:KHC:567" etc. First token is year, second is HC short code
# (2–6 upper-case letters optionally with a sub-bench suffix).
HC_NEUTRAL_RE = re.compile(
    r"\b(?P<year>\d{4}):(?P<court>[A-Z]{2,6}(?:-[A-Z]{1,4})?):(?P<seq>\d{1,6})\b"
)

# SCC family (incl. sub-series):
#   "(2019) 5 SCC 1"
#   "(2019) 3 SCC (Cri) 1"
#   "(2019) 4 SCC (L&S) 1"
#   "(2019) 2 SCC (Civ) 1"
SCC_RE = re.compile(
    r"""
    \(\s*(?P<year>\d{4})\s*\)\s*
    (?P<vol>\d{1,3})\s*
    SCC
    (?:\s*\(\s*(?P<sub>Cri|L&S|Civ)\s*\))?
    \s+(?P<page>\d{1,6})\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Supreme Court Reports (official): "(2018) 2 SCR 405" or "[2020] 3 SCR 1"
SCR_RE = re.compile(
    r"""
    [\(\[]\s*(?P<year>\d{4})\s*[\)\]]\s*
    (?P<vol>\d{1,3})\s+SCR\s+(?P<page>\d{1,6})\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# SCC OnLine: "2019 SCC OnLine SC 1234", "2019 SCC OnLine Del 456"
SCC_ONLINE_RE = re.compile(
    rf"""
    \b(?P<year>\d{{4}})\s+SCC\s+OnLine\s+
    (?P<court>{_COURT_ALT})
    \s+(?P<seq>\d{{1,6}})\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# AIR reporter: "AIR 2019 SC 123", "AIR 1973 SC 1461", "AIR 2019 Del 456"
AIR_RE = re.compile(
    rf"""
    \bAIR\s+(?P<year>\d{{4}})\s+
    (?P<court>{_COURT_ALT})
    \s+(?P<page>\d{{1,6}})\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Manupatra: "MANU/SC/0123/2019", "MANU/DE/0456/2021"
# Accept 3–6 digit seq and 2–6 letter court sub-codes.
MANU_RE = re.compile(
    r"\bMANU/(?P<court>[A-Z]{2,6})/(?P<seq>\d{3,6})/(?P<year>\d{4})\b"
)

# Indian Law Reports: "ILR (2019) Delhi 123", "ILR 2019 (2) Del 123"
ILR_RE = re.compile(
    rf"""
    \bILR\s+
    (?:\(\s*(?P<year1>\d{{4}})\s*\)|(?P<year2>\d{{4}}))
    (?:\s*\(\s*\d+\s*\))?
    \s+(?P<court>{_COURT_ALT})
    \s+(?P<page>\d{{1,6}})\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Criminal Law Journal: "2019 Cri LJ 1234", "2019 CrLJ 1234"
CRILJ_RE = re.compile(
    r"\b(?P<year>\d{4})\s+Cri\.?\s*LJ\s+(?P<page>\d{1,6})\b",
    re.IGNORECASE,
)

# Case title. Intentionally loose: the extractor runs this last and allows
# a trailing reporter citation to be merged in.  Parties can be 1–5 capitalised
# tokens each; reject lines that look like sentence fragments by requiring the
# 'v.' / 'vs.' token.
CASE_TITLE_RE = re.compile(
    r"""
    (?P<p1>
        (?:[A-Z][A-Za-z\.\-']+\.?)
        (?:\s+(?:of\s+)?[A-Z][A-Za-z\.\-']+\.?){0,5}
    )
    \s+v(?:s)?\.?\s+
    (?P<p2>
        (?:[A-Z][A-Za-z\.\-']+\.?)
        (?:\s+(?:of\s+)?[A-Z][A-Za-z\.\-']+\.?){0,5}
    )
    """,
    re.VERBOSE,
)


def normalise_court_code(raw: str) -> str:
    """Return the canonical court token for ``raw`` or ``'unknown'``.

    ``raw`` may be any of the strings found in :data:`COURT_CODE_TO_ID`
    (case-insensitive). Strings not in the table become ``'unknown'`` —
    callers should treat this as a soft signal that the citation parsed
    structurally but the court could not be resolved to our taxonomy.
    """
    key = raw.strip().lower()
    if key in COURT_CODE_TO_ID:
        return COURT_CODE_TO_ID[key]
    # Strip punctuation then retry (e.g. "P&H." -> "ph").
    stripped = re.sub(r"[^a-z&_]", "", key)
    return COURT_CODE_TO_ID.get(stripped, "unknown")


__all__ = [
    "COURT_CODE_TO_ID",
    "INSC_RE",
    "HC_NEUTRAL_RE",
    "SCC_RE",
    "SCR_RE",
    "SCC_ONLINE_RE",
    "AIR_RE",
    "MANU_RE",
    "ILR_RE",
    "CRILJ_RE",
    "CASE_TITLE_RE",
    "normalise_court_code",
]
