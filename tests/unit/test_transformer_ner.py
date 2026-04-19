"""Unit tests for :class:`TransformerLegalNER`.

The wrapper is designed to stay silent when the model can't be loaded so the
regex baseline keeps running. These tests pin that contract.
"""

from __future__ import annotations

import os

from services.lib.enrichment.legal_ner import Entity, LegalNER
from services.lib.enrichment.transformer_ner import TransformerLegalNER


def test_disabled_by_default_returns_empty(monkeypatch):
    monkeypatch.delenv("ENRICH_NER_ENABLED", raising=False)
    monkeypatch.delenv("ENRICH_NER_MODEL", raising=False)
    ner = TransformerLegalNER()
    assert ner.enabled is False
    assert ner.extract("Hon'ble Mr. Justice A.K. Sikri delivered the judgment.") == []


def test_enabled_without_model_stays_disabled(monkeypatch):
    monkeypatch.delenv("ENRICH_NER_MODEL", raising=False)
    ner = TransformerLegalNER(model_name=None, enabled=True)
    assert ner.enabled is False
    assert ner.extract("anything") == []


def test_unloadable_model_degrades_to_empty():
    # Intentionally unresolvable repo id. The wrapper must log + return [].
    ner = TransformerLegalNER(
        model_name="lexgraph-test/definitely-does-not-exist-xyz",
        enabled=True,
    )
    result = ner.extract("Mr. Justice Chandrachud presided.")
    assert result == []
    assert ner._load_failed is True  # noqa: SLF001 - white-box check


def test_legal_ner_runs_without_transformer():
    """Baseline regex NER must still produce entities when no transformer is wired."""
    ner = LegalNER(transformer=None)
    ents = ner.extract(
        "Hon'ble Mr. Justice A.K. Sikri of the Supreme Court of India held that "
        "Vishaka v. State of Rajasthan continues to govern."
    )
    types = {e.type for e in ents}
    assert "Court" in types
    assert "Judge" in types
    assert "Party" in types


def test_legal_ner_silently_ignores_failing_transformer():
    ner = LegalNER(
        transformer=TransformerLegalNER(
            model_name="lexgraph-test/definitely-does-not-exist-xyz",
            enabled=True,
        )
    )
    ents = ner.extract("Hon'ble Mr. Justice A.K. Sikri presided.")
    assert any(e.type == "Judge" for e in ents)
    # Every entity must still carry a source tag so downstream can audit.
    assert all(e.extra.get("source") == "regex" for e in ents)


class _StubTransformer:
    """Fake backend used to prove the composition path without downloading models."""

    def extract(self, text: str):
        # Pretend the model found an Organisation that the regex layer misses
        # entirely (no "v." anywhere, so PARTY_V_RE does not fire).
        word = "Reserve Bank of India"
        if word not in text:
            return []
        start = text.find(word)
        return [
            Entity(
                type="Organisation",
                text=word,
                start=start,
                end=start + len(word),
                extra={"source": "transformer", "score": "0.9876"},
            )
        ]


def test_legal_ner_merges_stub_transformer_output():
    ner = LegalNER(transformer=_StubTransformer())
    ents = ner.extract(
        "The Reserve Bank of India filed a statement before the Bombay High Court."
    )
    orgs = [e for e in ents if e.type == "Organisation"]
    # The Organisation entity only enters via the transformer backend.
    assert any(e.extra.get("source") == "transformer" for e in orgs)
    # Bombay High Court must still be picked up by the regex layer.
    assert any(e.type == "Court" and e.extra.get("source") == "regex" for e in ents)


def test_regex_wins_on_tied_span_collision():
    """Contract: when transformer and regex agree on the exact same span, the
    regex entity wins. That keeps the fully-tested layer authoritative."""

    # First, learn the span the regex layer actually emits for the judge name,
    # then build a collider that reports an entity at that exact span.
    baseline = LegalNER().extract("Hon'ble Mr. Justice A.K. Sikri delivered the judgment.")
    judge = next(e for e in baseline if e.type == "Judge")

    class _Collider:
        def extract(self, text: str):
            return [
                Entity(
                    type="Person",
                    text=judge.text,
                    start=judge.start,
                    end=judge.end,
                    extra={"source": "transformer"},
                )
            ]

    ner = LegalNER(transformer=_Collider())
    ents = ner.extract("Hon'ble Mr. Justice A.K. Sikri delivered the judgment.")
    at_span = [e for e in ents if e.start == judge.start and e.end == judge.end]
    assert len(at_span) == 1
    assert at_span[0].extra.get("source") == "regex"
    assert at_span[0].type == "Judge"
