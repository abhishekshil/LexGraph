from __future__ import annotations

from services.lib.retrieval.intent import QueryIntent, classify_intent


def test_crosswalk_intent():
    r = classify_intent("what is the corresponding BNS section for IPC 302?")
    assert r.intent == QueryIntent.CROSSWALK


def test_statute_intent():
    r = classify_intent("what is the law under Section 300 IPC?")
    assert r.intent == QueryIntent.STATUTE_LOOKUP


def test_private_intent():
    r = classify_intent("which exhibits support my case's allegation of common intention?",
                        has_matter=True)
    assert r.intent == QueryIntent.PRIVATE_EVIDENCE_CROSS


def test_ingredient_intent():
    r = classify_intent("what are the ingredients of the offence of theft?")
    assert r.intent == QueryIntent.OFFENCE_INGREDIENT
