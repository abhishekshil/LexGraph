"""Unit tests for services.lib.generation.

Covers the enforcement pass, provider selection / fallback, and end-to-end
behaviour of GroundedGenerator against a hand-built EvidencePack.
"""

from __future__ import annotations

import pytest

from services.lib.core import settings
from services.lib.data_models.evidence import EvidencePack, EvidenceSpan
from services.lib.generation import (
    GroundedGenerator,
    StubProvider,
    enforce,
    format_answer,
    get_provider,
    reset_provider_cache,
)
from services.lib.generation.providers import HFProvider, OpenAIProvider
from services.lib.ontology.authority import AuthorityTier


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _span(marker: str, *, tier: int = 1, kind: str = "public", **kw) -> EvidenceSpan:
    return EvidenceSpan(
        marker=marker,
        node_id=kw.get("node_id", f"node_{marker}"),
        node_type=kw.get("node_type", "Section"),
        source_span_id=kw.get("source_span_id", f"span_{marker}"),
        source_episode_id=kw.get("source_episode_id", "ep_1"),
        file_id=kw.get("file_id", "file_1"),
        title=kw.get("title", "Section 378 IPC"),
        citation=kw.get("citation"),
        section_or_paragraph=kw.get("section_or_paragraph", "Section 378 IPC"),
        court=kw.get("court"),
        date=kw.get("date"),
        excerpt=kw.get(
            "excerpt",
            "Whoever, intending to take dishonestly any movable property out of "
            "the possession of any person without that person's consent...",
        ),
        page=None,
        char_start=0,
        char_end=120,
        tier=AuthorityTier(tier),
        score=1.0,
        kind=kind,  # type: ignore[arg-type]
        matter_id=kw.get("matter_id"),
    )


def _pack(*spans: EvidenceSpan, **kw) -> EvidencePack:
    return EvidencePack(
        query=kw.get("query", "What is theft under S. 378 IPC?"),
        query_type=kw.get("query_type", "statute_lookup"),
        intent={},
        spans=list(spans),
        graph_paths=[],
        conflicts=kw.get("conflicts", []),
        matter_scope=kw.get("matter_scope"),
        confidence=kw.get("confidence", "medium"),
        insufficient_evidence=kw.get("insufficient_evidence", False),
        retrieval_debug={},
    )


# ---------------------------------------------------------------------------
# Enforcement
# ---------------------------------------------------------------------------


def test_enforce_keeps_grounded_sentences_and_drops_bare_claims():
    pack = _pack(_span("S1"), _span("S2", tier=2))
    raw = (
        "Answer: Theft is defined in Section 378 IPC. [S1] The punishment is in "
        "Section 379 IPC. [S2] Historically, the concept comes from common law.\n"
        "Legal basis:\n- Section 378 IPC [S1]\n- Section 379 IPC [S2]\n"
        "Confidence: HIGH\nInsufficient evidence: NO\n"
    )
    clean, report = enforce(raw, pack)
    assert "Theft is defined" in clean.answer
    assert "common law" not in clean.answer  # uncited sentence dropped
    assert clean.confidence == "high"
    assert clean.insufficient is False
    assert {"S1", "S2"} <= clean.used_markers
    assert report.kept_sentences == 2
    assert len(report.dropped_sentences) == 1


def test_enforce_strips_fabricated_markers_but_keeps_sentence_if_valid_remains():
    pack = _pack(_span("S1"))
    raw = (
        "Answer: Theft is defined in Section 378 IPC [S1] and also in a ghost "
        "source [S99]. [S1]\n"
        "Confidence: LOW\nInsufficient evidence: NO\n"
    )
    clean, report = enforce(raw, pack)
    assert "S99" not in clean.answer
    assert "S1" in clean.answer
    assert "S99" in report.fabricated_markers
    assert clean.insufficient is False


def test_enforce_drops_sentence_that_only_cites_fabricated_markers():
    pack = _pack(_span("S1"))
    raw = (
        "Answer: This is real [S1]. This is fake [S42].\n"
        "Confidence: MEDIUM\nInsufficient evidence: NO\n"
    )
    clean, report = enforce(raw, pack)
    assert "fake" not in clean.answer
    assert "real" in clean.answer
    assert "S42" in report.fabricated_markers


def test_enforce_forces_insufficient_when_all_sentences_are_dropped():
    pack = _pack(_span("S1"))
    raw = "Answer: nothing here is cited.\nConfidence: HIGH\nInsufficient evidence: NO\n"
    clean, _ = enforce(raw, pack)
    assert clean.insufficient is True
    assert clean.confidence == "low"
    assert clean.answer == ""


def test_enforce_parses_bulleted_legal_basis():
    pack = _pack(_span("S1", title="S.378 IPC"), _span("S2", title="S.379 IPC", tier=1))
    raw = (
        "Answer: Theft is covered by Section 378. [S1]\n"
        "Legal basis:\n* Section 378 IPC — definition [S1]\n"
        "* Section 379 IPC — punishment [S2]\n"
        "* A fabricated case [S99]\n"
        "Confidence: HIGH\nInsufficient evidence: NO\n"
    )
    clean, report = enforce(raw, pack)
    assert any("Section 378" in b for b in clean.legal_basis)
    assert any("Section 379" in b for b in clean.legal_basis)
    assert not any("fabricated" in b for b in clean.legal_basis)
    assert "S99" in report.fabricated_markers


def test_format_answer_renders_canonical_layout():
    pack = _pack(_span("S1"))
    raw = "Answer: Theft is defined in S.378. [S1]\nConfidence: HIGH\nInsufficient evidence: NO\n"
    clean, _ = enforce(raw, pack)
    rendered = format_answer(clean)
    assert rendered.startswith("Answer:")
    assert "Confidence: HIGH" in rendered
    assert "Insufficient evidence: NO" in rendered


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------


def test_stub_provider_always_cites_markers_from_pack():
    import asyncio

    pack_text = "[S1] header\nbody\n---\n[S2] header\nbody\n---\n"
    out = asyncio.run(StubProvider().complete(question="q?", evidence_pack_text=pack_text))
    assert "[S1]" in out and "[S2]" in out
    assert "Confidence:" in out
    assert "Insufficient evidence:" in out


def test_stub_provider_says_insufficient_when_no_markers():
    import asyncio

    out = asyncio.run(StubProvider().complete(question="q?", evidence_pack_text=""))
    assert "Insufficient evidence: YES" in out


def test_get_provider_picks_stub_when_no_openai_key(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "generation_provider", "openai")
    reset_provider_cache()
    p = get_provider()
    assert isinstance(p, StubProvider)
    reset_provider_cache()


def test_get_provider_auto_mode(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "generation_provider", "auto")
    reset_provider_cache()
    assert isinstance(get_provider(), StubProvider)
    reset_provider_cache()
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    reset_provider_cache()
    assert isinstance(get_provider(), OpenAIProvider)
    reset_provider_cache()


def test_get_provider_hf_mode_falls_back_when_transformers_missing(monkeypatch):
    # transformers isn't installed in the minimal test env → the HF provider
    # returns a stub on first call without raising.
    monkeypatch.setattr(settings, "generation_provider", "hf")
    reset_provider_cache()
    p = get_provider()
    assert isinstance(p, HFProvider)
    # Triggering _ensure should set the fallback silently.
    assert p._ensure() is False
    assert p._fallback is not None
    reset_provider_cache()


# ---------------------------------------------------------------------------
# GroundedGenerator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generator_refuses_when_pack_insufficient():
    pack = _pack(_span("S1"), insufficient_evidence=True)
    gen = GroundedGenerator(provider=StubProvider())
    answer = await gen.generate(pack, trace_id="t-refuse")
    assert answer.insufficient_evidence is True
    assert answer.confidence == "low"
    assert answer.legal_basis == []
    assert "refusal:retrieval_insufficient" in answer.notes


@pytest.mark.asyncio
async def test_generator_produces_grounded_answer_with_stub_provider():
    pack = _pack(
        _span("S1", tier=1, title="Section 378 IPC"),
        _span("S2", tier=1, title="Section 379 IPC"),
    )
    gen = GroundedGenerator(provider=StubProvider())
    answer = await gen.generate(pack, trace_id="t-stub")
    assert answer.insufficient_evidence is False
    assert answer.legal_basis, "expected at least one citation"
    assert {c.marker for c in answer.legal_basis} <= {"S1", "S2"}
    assert answer.extras.get("provider") == "stub"
    assert "[S1]" in answer.answer


@pytest.mark.asyncio
async def test_generator_refuses_when_provider_hallucinates_everything():
    class HallucinatingProvider:
        name = "hallu"

        async def complete(self, *, question: str, evidence_pack_text: str) -> str:
            # Only cites markers that don't exist in the pack.
            return (
                "Answer: This comes from [S99] and [S100].\n"
                "Confidence: HIGH\n"
                "Insufficient evidence: NO\n"
            )

    pack = _pack(_span("S1"))
    gen = GroundedGenerator(provider=HallucinatingProvider())  # type: ignore[arg-type]
    answer = await gen.generate(pack, trace_id="t-hallu")
    assert answer.insufficient_evidence is True
    assert "refusal:enforcement_empty" in answer.notes


@pytest.mark.asyncio
async def test_generator_falls_back_to_stub_when_provider_throws():
    class ExplodingProvider:
        name = "boom"

        async def complete(self, *, question: str, evidence_pack_text: str) -> str:
            raise RuntimeError("connection reset")

    pack = _pack(_span("S1"))
    gen = GroundedGenerator(provider=ExplodingProvider())  # type: ignore[arg-type]
    answer = await gen.generate(pack, trace_id="t-boom")
    # Stub still produced something grounded.
    assert answer.insufficient_evidence is False
    assert answer.legal_basis


@pytest.mark.asyncio
async def test_generator_renders_conflicts_and_private_material():
    private = _span(
        "S2",
        tier=6,
        kind="private",
        node_type="Exhibit",
        title="Exhibit P-3",
        matter_id="m1",
    )
    pack = _pack(
        _span("S1", tier=1, title="Section 378 IPC"),
        private,
        conflicts=[
            {
                "description": "SC and HC disagree on ingredient X.",
                "markers": ["S1"],
                "tiers": [1, 3],
            }
        ],
    )
    gen = GroundedGenerator(provider=StubProvider())
    answer = await gen.generate(pack, trace_id="t-conflicts")
    assert any(c.marker == "S2" for c in answer.supporting_private_sources)
    assert answer.conflicts and answer.conflicts[0].severity == "high"
