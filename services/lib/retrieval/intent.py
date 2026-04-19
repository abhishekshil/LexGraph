"""Rule-based query-intent classifier.

Bootstraps retrieval without requiring an LLM call per query. It is
deliberately extensible: add (pattern, intent) pairs and you get new routing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class QueryIntent(StrEnum):
    STATUTE_LOOKUP = "statute_lookup"
    CASE_LAW_RETRIEVAL = "case_law_retrieval"
    PRECEDENT_TRACING = "precedent_tracing"
    OFFENCE_INGREDIENT = "offence_ingredient"
    PUNISHMENT_LOOKUP = "punishment_lookup"
    PROCEDURE_LOOKUP = "procedure_lookup"
    EVIDENCE_RULE_LOOKUP = "evidence_rule_lookup"
    CROSSWALK = "crosswalk_old_new"
    AUTHORITY_FOR_ISSUE = "authority_for_issue"
    PRIVATE_EVIDENCE_CROSS = "private_evidence_cross_analysis"
    CONTRADICTION = "contradiction_detection"
    TIMELINE = "timeline_reconstruction"
    AUTHORITY_CONFLICT = "authority_conflict"
    GENERIC = "generic"


@dataclass
class IntentResult:
    intent: QueryIntent
    signals: dict[str, str]


_PATTERNS: list[tuple[re.Pattern[str], QueryIntent]] = [
    (re.compile(r"\b(ingredients?|elements?)\b.*\b(offence|crime)\b", re.I), QueryIntent.OFFENCE_INGREDIENT),
    (re.compile(r"\b(punishment|sentence|penalty)\b", re.I), QueryIntent.PUNISHMENT_LOOKUP),
    (re.compile(r"\b(procedure|how\s+to|what\s+is\s+the\s+process)\b", re.I), QueryIntent.PROCEDURE_LOOKUP),
    (re.compile(r"\b(evidence\s+rule|admissib|presumption|burden\s+of\s+proof)\b", re.I), QueryIntent.EVIDENCE_RULE_LOOKUP),
    (re.compile(r"\b(IPC.*BNS|BNS.*IPC|CrPC.*BNSS|BNSS.*CrPC|IEA.*BSA|BSA.*IEA|equivalent|corresponding\s+section|map(?:ping)?)\b", re.I), QueryIntent.CROSSWALK),
    (re.compile(r"\b(precedent|leading\s+case|landmark|overrul|distinguish|follow)\b", re.I), QueryIntent.PRECEDENT_TRACING),
    (re.compile(r"\b(contradict|inconsistent|discrepanc)\b", re.I), QueryIntent.CONTRADICTION),
    (re.compile(r"\b(timeline|sequence\s+of\s+events|chronolog)\b", re.I), QueryIntent.TIMELINE),
    (re.compile(r"\b(exhibit|witness|chargesheet|fir|plaint|affidavit|matter|my\s+case)\b", re.I), QueryIntent.PRIVATE_EVIDENCE_CROSS),
    (re.compile(r"\b(which\s+judgments?|interpret|interpretation)\b", re.I), QueryIntent.CASE_LAW_RETRIEVAL),
    (re.compile(r"\b(what\s+is\s+(?:the\s+)?(?:law|provision)|section\s+\d|article\s+\d)\b", re.I), QueryIntent.STATUTE_LOOKUP),
]


def classify_intent(question: str, *, has_matter: bool = False) -> IntentResult:
    signals: dict[str, str] = {}
    for pat, intent in _PATTERNS:
        m = pat.search(question)
        if m:
            signals["matched"] = m.group(0)
            return IntentResult(intent=intent, signals=signals)
    if has_matter and re.search(r"\b(my|this|our)\b", question, re.I):
        return IntentResult(QueryIntent.PRIVATE_EVIDENCE_CROSS, signals)
    return IntentResult(QueryIntent.GENERIC, signals)
