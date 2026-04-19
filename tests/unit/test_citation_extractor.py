"""Unit tests for the Indian legal citation extractor.

Each test pins one reporter format to:

* the ``kind`` (neutral / reporter / case_title / combined)
* the canonical id schema (so the graph writer keeps MERGE semantics)
* the court and year parsed out of the raw string

If you add a new pattern, add a test here *before* touching
:mod:`citation_patterns` so the canonical id contract stays pinned.
"""

from __future__ import annotations

import pytest

from services.lib.enrichment import extract_citations
from services.lib.enrichment.citation_extractor import Citation


def _find(cits: list[Citation], raw_contains: str) -> Citation:
    for c in cits:
        if raw_contains.lower() in c.raw.lower():
            return c
    raise AssertionError(f"no citation matched {raw_contains!r} in {cits!r}")


# ---------------------------------------------------------------------------
# Neutral citations
# ---------------------------------------------------------------------------

def test_insc_neutral():
    cits = extract_citations("See 2023 INSC 845 for the latest view.")
    c = _find(cits, "2023 INSC 845")
    assert c.kind == "neutral"
    assert c.canonical_id == "case:sc:insc:2023:845"
    assert c.court == "sc"
    assert c.year == 2023
    assert c.reporter == "insc"
    assert c.seq == "845"


def test_hc_neutral_delhi():
    cits = extract_citations("Relying on 2023:DHC:1234, the bench held...")
    c = _find(cits, "2023:DHC:1234")
    assert c.kind == "neutral"
    assert c.canonical_id == "case:del:neutral:2023:1234"
    assert c.court == "del"


def test_hc_neutral_with_bench_suffix():
    cits = extract_citations("As per 2022:BHC-AS:1234 (Aurangabad bench)...")
    c = _find(cits, "2022:BHC-AS:1234")
    assert c.court == "bom"
    assert c.canonical_id == "case:bom:neutral:2022:1234"
    assert c.extras.get("hc_code", "").upper() == "BHC-AS"


def test_hc_neutral_unknown_code_is_dropped():
    # ZZZ is not a real court code and must not leak into the graph.
    cits = extract_citations("junk 2023:ZZZ:1 fake")
    assert not any(c.kind == "neutral" and c.court == "unknown" for c in cits)


# ---------------------------------------------------------------------------
# SCC family
# ---------------------------------------------------------------------------

def test_scc_main():
    cits = extract_citations("(2019) 5 SCC 1 is the foundational ruling.")
    c = _find(cits, "(2019) 5 SCC 1")
    assert c.kind == "reporter"
    assert c.canonical_id == "case:sc:scc:2019:5:1"
    assert c.volume == "5" and c.page == "1"


def test_scc_criminal_subseries():
    c = _find(
        extract_citations("Relying on (2019) 3 SCC (Cri) 1, the Court..."),
        "(2019) 3 SCC (Cri) 1",
    )
    assert c.reporter == "scc_cri"
    assert c.canonical_id == "case:sc:scc_cri:2019:3:1"


def test_scc_labour_subseries():
    c = _find(
        extract_citations("see (2019) 4 SCC (L&S) 1"),
        "(2019) 4 SCC (L&S) 1",
    )
    assert c.reporter == "scc_ls"
    assert c.canonical_id == "case:sc:scc_ls:2019:4:1"


def test_scc_civil_subseries():
    c = _find(
        extract_citations("see (2019) 2 SCC (Civ) 1"),
        "(2019) 2 SCC (Civ) 1",
    )
    assert c.reporter == "scc_civ"


# ---------------------------------------------------------------------------
# SCR
# ---------------------------------------------------------------------------

def test_scr_parentheses():
    c = _find(
        extract_citations("Originally reported at (2018) 2 SCR 405."),
        "(2018) 2 SCR 405",
    )
    assert c.reporter == "scr"
    assert c.canonical_id == "case:sc:scr:2018:2:405"


def test_scr_square_brackets():
    c = _find(
        extract_citations("Also [2020] 3 SCR 1."),
        "[2020] 3 SCR 1",
    )
    assert c.canonical_id == "case:sc:scr:2020:3:1"


# ---------------------------------------------------------------------------
# SCC OnLine
# ---------------------------------------------------------------------------

def test_scc_online_sc():
    c = _find(
        extract_citations("See 2019 SCC OnLine SC 1234."),
        "2019 SCC OnLine SC 1234",
    )
    assert c.canonical_id == "case:sc:scc_online:2019:1234"


def test_scc_online_delhi():
    c = _find(
        extract_citations("Per 2019 SCC OnLine Del 456."),
        "2019 SCC OnLine Del 456",
    )
    assert c.court == "del"
    assert c.canonical_id == "case:del:scc_online:2019:456"


# ---------------------------------------------------------------------------
# AIR
# ---------------------------------------------------------------------------

def test_air_supreme_court():
    c = _find(
        extract_citations("Authority: AIR 1973 SC 1461."),
        "AIR 1973 SC 1461",
    )
    assert c.canonical_id == "case:sc:air:1973:1461"
    assert c.court == "sc" and c.year == 1973


def test_air_high_court():
    c = _find(
        extract_citations("Also AIR 2019 Del 456."),
        "AIR 2019 Del 456",
    )
    assert c.court == "del"
    assert c.canonical_id == "case:del:air:2019:456"


# ---------------------------------------------------------------------------
# Manupatra
# ---------------------------------------------------------------------------

def test_manu_supreme_court():
    c = _find(
        extract_citations("cf. MANU/SC/0123/2019."),
        "MANU/SC/0123/2019",
    )
    assert c.canonical_id == "case:sc:manu:0123:2019"
    assert c.court == "sc"


def test_manu_delhi_subcode():
    c = _find(
        extract_citations("cf. MANU/DE/0456/2021."),
        "MANU/DE/0456/2021",
    )
    # MANU uses DE for Delhi; our mapper normalises it.
    assert c.court == "del"
    assert c.canonical_id == "case:del:manu:0456:2021"


# ---------------------------------------------------------------------------
# ILR / CriLJ
# ---------------------------------------------------------------------------

def test_ilr_parenthesised_year():
    c = _find(
        extract_citations("Reported at ILR (2019) Delhi 123."),
        "ILR (2019) Delhi 123",
    )
    assert c.court == "del" and c.year == 2019
    assert c.canonical_id == "case:del:ilr:2019:123"


def test_crilj_no_court_token():
    c = _find(
        extract_citations("Also 2019 Cri LJ 1234."),
        "2019 Cri LJ 1234",
    )
    assert c.court == "unknown"
    assert c.canonical_id == "case:unknown:crilj:2019:1234"


# ---------------------------------------------------------------------------
# Case titles and merge behaviour
# ---------------------------------------------------------------------------

def test_bare_case_title():
    c = _find(
        extract_citations("The ratio in Vishaka v. State of Rajasthan applies."),
        "Vishaka v. State of Rajasthan",
    )
    assert c.kind == "case_title"
    assert c.parties == ("Vishaka", "State of Rajasthan")
    assert c.canonical_id == "case:title:vishaka_v_state_of_rajasthan"


def test_title_merges_with_trailing_citation():
    cits = extract_citations(
        "See Vishaka v. State of Rajasthan, (1997) 6 SCC 241."
    )
    # Exactly one combined record should be produced, covering both halves.
    combined = [c for c in cits if c.kind == "combined"]
    assert len(combined) == 1
    c = combined[0]
    # Canonical id comes from the reporter citation (precise + stable).
    assert c.canonical_id == "case:sc:scc:1997:6:241"
    # Parties come from the title.
    assert c.parties == ("Vishaka", "State of Rajasthan")
    # The raw span covers the whole fused citation, not just the title.
    assert "Vishaka" in c.raw and "(1997) 6 SCC 241" in c.raw


def test_title_and_citation_without_comma_still_merge():
    cits = extract_citations("Vishaka v. State of Rajasthan (1997) 6 SCC 241")
    assert any(c.kind == "combined" for c in cits)


def test_multiple_distinct_citations_are_all_kept():
    text = (
        "We rely on (2019) 5 SCC 1 and also AIR 1973 SC 1461 "
        "as well as 2023 INSC 845."
    )
    ids = {c.canonical_id for c in extract_citations(text)}
    assert "case:sc:scc:2019:5:1" in ids
    assert "case:sc:air:1973:1461" in ids
    assert "case:sc:insc:2023:845" in ids


def test_year_bounds_reject_nonsense():
    # Year 1500 is below _MIN_YEAR; year 3000 is above _MAX_YEAR.
    cits = extract_citations("fake 1500 INSC 1 and fake 3000 INSC 2")
    assert cits == []


# ---------------------------------------------------------------------------
# Dedupe behaviour
# ---------------------------------------------------------------------------

def test_overlap_prefers_combined_over_fragments():
    text = "Vishaka v. State of Rajasthan, (1997) 6 SCC 241 is seminal."
    kinds = sorted(c.kind for c in extract_citations(text))
    # After merging + dedupe we should see one `combined` record, and none
    # of the fragmentary `case_title` / `reporter` left behind.
    assert "combined" in kinds
    assert "case_title" not in kinds
    assert "reporter" not in kinds


@pytest.mark.parametrize(
    "raw",
    [
        "2023 INSC 845",
        "(2019) 5 SCC 1",
        "(2018) 2 SCR 405",
        "AIR 1973 SC 1461",
        "MANU/SC/0123/2019",
        "2019 SCC OnLine Del 456",
        "2023:DHC:1234",
    ],
)
def test_all_primary_formats_produce_case_canonical_id(raw: str):
    cits = extract_citations(f"prefix {raw} suffix")
    assert cits, f"no citation found for {raw}"
    c = cits[0]
    assert c.canonical_id.startswith("case:")
    # canonical ids must never contain whitespace — they become graph node ids.
    assert " " not in c.canonical_id
