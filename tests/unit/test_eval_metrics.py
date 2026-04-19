"""Unit tests for evaluation metrics + threshold checking."""

from __future__ import annotations

from services.lib.evaluation import (
    EvaluationReport,
    check_thresholds,
)
from services.lib.evaluation.metrics import (
    citation_faithfulness,
    crosswalk_mapping_accuracy,
    fabricated_marker_rate,
    false_refusal_rate,
    grounding_rate,
    latency_stats,
    pack_utilisation,
    refusal_rate,
    retrieval_coverage,
    retrieval_hit_rate,
    span_citation_correctness,
    tier1_anchor_rate,
    true_refusal_rate,
    unsupported_claim_rate,
)
from services.lib.evaluation.report import DatasetReport, EvaluationSummary, ItemResult


def _item(**kw):
    return {
        "answer": kw.get("answer", ""),
        "pack_spans": kw.get("pack_spans", []),
        "pack_tiers": kw.get("pack_tiers", []),
        "pack_node_ids": kw.get("pack_node_ids", []),
        "citations": kw.get("citations", []),
        "gold": kw.get("gold", {}),
        "insufficient_evidence": kw.get("insufficient_evidence", False),
        "latency_s": kw.get("latency_s", 0.1),
    }


# ---------------------------------------------------------------------------
# Grounding
# ---------------------------------------------------------------------------


def test_grounding_rate_counts_claim_sentences_only():
    results = [
        _item(
            answer=(
                "Answer:\n"
                "Theft is defined in Section 378 IPC [S1]. "
                "Punishment is three years [S2]. "
                "This is historical context."
            ),
            pack_spans=["1", "2"],
        )
    ]
    # Three claim sentences: two cited, one uncited → 2/3. The "Answer:"
    # header line is stripped by the splitter.
    g = grounding_rate(results)
    assert abs(g - 2 / 3) < 1e-6
    assert unsupported_claim_rate(results) == 1.0 - g


def test_fabricated_marker_rate_detects_invented_citations():
    results = [
        _item(answer="Theft [S1] and [S99] and [S1].", pack_spans=["1"])
    ]
    assert abs(fabricated_marker_rate(results) - 1 / 3) < 1e-6


def test_citation_faithfulness_complements_fabrication():
    results = [_item(answer="[S1] [S2] [S99]", pack_spans=["1", "2"])]
    assert abs(citation_faithfulness(results) - 2 / 3) < 1e-6


# ---------------------------------------------------------------------------
# Citation + retrieval structural
# ---------------------------------------------------------------------------


def test_span_citation_correctness_needs_excerpt_and_span_id():
    results = [
        _item(
            citations=[
                {"excerpt": "x", "source_span_id": "sp1"},
                {"excerpt": "y", "source_span_id": ""},
                {"excerpt": "", "source_span_id": "sp3"},
            ]
        )
    ]
    assert span_citation_correctness(results) == 1 / 3


def test_pack_utilisation_measures_cited_fraction():
    results = [
        _item(answer="[S1] [S1] [S3]", pack_spans=["1", "2", "3"])  # 2/3 unique used
    ]
    assert abs(pack_utilisation(results) - 2 / 3) < 1e-6


def test_tier1_anchor_rate_requires_any_tier1_span():
    results = [
        _item(pack_tiers=[2, 3]),
        _item(pack_tiers=[1, 2]),
        _item(pack_tiers=[8]),
    ]
    assert abs(tier1_anchor_rate(results) - 1 / 3) < 1e-6


def test_retrieval_hit_rate_matches_sections_or_nodes():
    results = [
        _item(
            citations=[{"section_or_paragraph": "Section 378 IPC"}],
            gold={"expected_sections": ["Section 378"]},
        ),
        _item(
            pack_node_ids=["section:ipc:378"],
            gold={"expected_node_ids": ["section:ipc:378"]},
        ),
        _item(
            citations=[{"section_or_paragraph": "Other"}],
            gold={"expected_sections": ["Section 999"]},
        ),
    ]
    assert abs(retrieval_hit_rate(results) - 2 / 3) < 1e-6


def test_retrieval_coverage_counts_non_empty_packs():
    results = [
        _item(pack_spans=["1"]),
        _item(pack_spans=[]),
        _item(pack_spans=["1", "2"]),
    ]
    assert retrieval_coverage(results) == 2 / 3


# ---------------------------------------------------------------------------
# Refusal
# ---------------------------------------------------------------------------


def test_refusal_rates_classify_answerable_and_unanswerable():
    results = [
        _item(insufficient_evidence=False, gold={"expected_sections": ["S.1"]}),
        _item(insufficient_evidence=True, gold={"expected_sections": ["S.2"]}),
        _item(insufficient_evidence=True, gold={}),
        _item(insufficient_evidence=False, gold={}),
    ]
    assert refusal_rate(results) == 0.5
    # One answerable was refused → false refusal 1/2.
    assert false_refusal_rate(results) == 0.5
    # One of the two unanswerable was refused → true refusal 1/2.
    assert true_refusal_rate(results) == 0.5


# ---------------------------------------------------------------------------
# Crosswalk
# ---------------------------------------------------------------------------


def test_crosswalk_mapping_accuracy_looks_at_citation_section_label():
    results = [
        _item(
            citations=[{"section_or_paragraph": "Section 303 BNS"}],
            gold={"expected_mapping": {"source": "s.378 ipc", "target": "303"}},
        ),
        _item(
            citations=[{"section_or_paragraph": "Section 500 BNS"}],
            gold={"expected_mapping": {"source": "s.300 ipc", "target": "101"}},
        ),
    ]
    assert crosswalk_mapping_accuracy(results) == 0.5


# ---------------------------------------------------------------------------
# Latency
# ---------------------------------------------------------------------------


def test_latency_stats_returns_percentiles():
    results = [_item(latency_s=x) for x in (0.1, 0.2, 0.3, 0.4, 0.5)]
    stats = latency_stats(results)
    assert stats["max"] == 0.5
    assert 0.2 <= stats["p50"] <= 0.4
    assert stats["p95"] >= 0.4


# ---------------------------------------------------------------------------
# Threshold gating
# ---------------------------------------------------------------------------


def _summary(**kw) -> EvaluationSummary:
    base = dict(
        items=1,
        grounding_rate=1.0,
        unsupported_claim_rate=0.0,
        fabricated_marker_rate=0.0,
        citation_faithfulness=1.0,
        span_citation_correctness=1.0,
        pack_utilisation=0.5,
        tier1_anchor_rate=1.0,
        retrieval_hit_rate=1.0,
        retrieval_coverage=1.0,
        refusal_rate=0.0,
        false_refusal_rate=0.0,
        true_refusal_rate=1.0,
        crosswalk_mapping_accuracy=1.0,
        latency_mean_s=0.05,
        latency_p50_s=0.05,
        latency_p95_s=0.08,
        latency_max_s=0.1,
    )
    base.update(kw)
    return EvaluationSummary(**base)


def test_check_thresholds_passes_when_all_metrics_ok():
    report = EvaluationReport(
        datasets=[DatasetReport(dataset="ds1", summary=_summary(), results=[])]
    )
    thresholds = {"_default": {"min": {"grounding_rate": 0.9}, "max": {"fabricated_marker_rate": 0.05}}}
    assert check_thresholds(report, thresholds) == []


def test_check_thresholds_flags_min_violations():
    report = EvaluationReport(
        datasets=[DatasetReport(dataset="ds1", summary=_summary(grounding_rate=0.5), results=[])]
    )
    thresholds = {"_default": {"min": {"grounding_rate": 0.9}}}
    v = check_thresholds(report, thresholds)
    assert len(v) == 1
    assert v[0].metric == "grounding_rate"
    assert v[0].kind == "min"
    assert v[0].observed == 0.5


def test_check_thresholds_flags_max_violations():
    report = EvaluationReport(
        datasets=[DatasetReport(dataset="ds1", summary=_summary(fabricated_marker_rate=0.2), results=[])]
    )
    thresholds = {"ds1": {"max": {"fabricated_marker_rate": 0.05}}}
    v = check_thresholds(report, thresholds)
    assert len(v) == 1
    assert v[0].metric == "fabricated_marker_rate"
    assert v[0].kind == "max"


def test_check_thresholds_dataset_overrides_merge_over_default():
    report = EvaluationReport(
        datasets=[
            DatasetReport(
                dataset="ds1",
                summary=_summary(grounding_rate=0.85, tier1_anchor_rate=0.5),
                results=[],
            )
        ]
    )
    thresholds = {
        "_default": {"min": {"grounding_rate": 0.9, "tier1_anchor_rate": 0.9}},
        "ds1": {"min": {"grounding_rate": 0.8}},  # relaxed
    }
    v = check_thresholds(report, thresholds)
    # tier1_anchor_rate from default still applies → one violation.
    metrics = {x.metric for x in v}
    assert metrics == {"tier1_anchor_rate"}


# ---------------------------------------------------------------------------
# Report round-trip
# ---------------------------------------------------------------------------


def test_report_serialises_to_json():
    report = EvaluationReport(
        datasets=[
            DatasetReport(
                dataset="ds1",
                summary=_summary(),
                results=[
                    ItemResult(
                        id="i1",
                        question="q",
                        answer="a",
                        pack_spans=["1"],
                        pack_tiers=[1],
                    )
                ],
            )
        ]
    )
    s = report.to_json()
    assert "ds1" in s and "i1" in s
