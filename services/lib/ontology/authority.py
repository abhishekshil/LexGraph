"""Authority tiers per docs/architecture.md §5.

Tiers drive ranking, evidence selection, and conflict surfacing. A smaller
number means higher authority.
"""

from __future__ import annotations

from enum import IntEnum

from .node_types import NodeType


class AuthorityTier(IntEnum):
    CONSTITUTION_STATUTE = 1
    SUPREME_COURT = 2
    HIGH_COURT = 3
    TRIBUNAL = 4
    LOWER_COURT = 5
    PRIVATE_CASE_DOC = 6
    PRIVATE_NOTE = 7
    AI_SUMMARY = 8


# Default mapping from node type → tier. Several types (Case, Paragraph) need
# context (which court?) and are resolved at write-time by authority_tier_for().
AUTHORITY_TIER_RULES: dict[NodeType, AuthorityTier] = {
    # tier 1
    NodeType.CONSTITUTION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.ACT: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.AMENDMENT: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.PART: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.CHAPTER: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.SECTION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.SUBSECTION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.PROVISO: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.EXPLANATION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.ILLUSTRATION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.RULE: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.REGULATION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.NOTIFICATION: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.CIRCULAR: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.SCHEDULE: AuthorityTier.CONSTITUTION_STATUTE,
    # judicial handled below by context
    # offence/procedure/evidence track the governing section's tier
    NodeType.OFFENCE: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.INGREDIENT: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.PUNISHMENT: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.PROCEDURE: AuthorityTier.CONSTITUTION_STATUTE,
    NodeType.EVIDENCE_RULE: AuthorityTier.CONSTITUTION_STATUTE,
    # private
    NodeType.MATTER: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.DOCUMENT: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.WITNESS: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.STATEMENT: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.EXHIBIT: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.FACT: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.TIMELINE_EVENT: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.ALLEGATION: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.DEFENSE: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.CONTRADICTION: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.MEDICAL_RECORD: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.FORENSIC_RECORD: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.NOTICE: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.CONTRACT_CLAUSE: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.COMMUNICATION: AuthorityTier.PRIVATE_CASE_DOC,
    NodeType.ARGUMENT: AuthorityTier.PRIVATE_NOTE,
    # derived
    NodeType.SUMMARY_NODE: AuthorityTier.AI_SUMMARY,
    NodeType.EXTRACTED_CLAIM: AuthorityTier.AI_SUMMARY,
}


_COURT_LEVEL_TO_TIER = {
    "SC": AuthorityTier.SUPREME_COURT,
    "SUPREME_COURT": AuthorityTier.SUPREME_COURT,
    "HC": AuthorityTier.HIGH_COURT,
    "HIGH_COURT": AuthorityTier.HIGH_COURT,
    "TRIBUNAL": AuthorityTier.TRIBUNAL,
    "NCLAT": AuthorityTier.TRIBUNAL,
    "NGT": AuthorityTier.TRIBUNAL,
    "ITAT": AuthorityTier.TRIBUNAL,
    "CAT": AuthorityTier.TRIBUNAL,
    "LOWER": AuthorityTier.LOWER_COURT,
    "DISTRICT": AuthorityTier.LOWER_COURT,
    "SESSIONS": AuthorityTier.LOWER_COURT,
    "MAGISTRATE": AuthorityTier.LOWER_COURT,
}


def authority_tier_for(node_type: NodeType, *, court_level: str | None = None) -> AuthorityTier:
    """Return the tier for a node.

    For judicial nodes (Case/Holding/Paragraph/Ratio/...) the court level must
    be supplied; otherwise this falls back to a conservative HIGH_COURT default
    so we never silently over-promote.
    """
    if node_type in AUTHORITY_TIER_RULES:
        return AUTHORITY_TIER_RULES[node_type]

    judicial = {
        NodeType.CASE,
        NodeType.HOLDING,
        NodeType.RATIO,
        NodeType.OBITER,
        NodeType.PARAGRAPH,
        NodeType.ISSUE,
        NodeType.LEGAL_TEST,
        NodeType.DOCTRINE,
        NodeType.PRECEDENT,
        NodeType.RELIEF,
        NodeType.OUTCOME,
        NodeType.PROCEDURAL_STAGE,
        NodeType.CITATION,
        NodeType.BENCH,
        NodeType.JUDGE,
        NodeType.COURT,
        NodeType.PARTY,
    }
    if node_type in judicial:
        if court_level is None:
            return AuthorityTier.HIGH_COURT
        return _COURT_LEVEL_TO_TIER.get(court_level.upper(), AuthorityTier.HIGH_COURT)

    # system / provenance nodes are tier-less; we report AI_SUMMARY as a safe
    # default (they should never be used as primary citations anyway).
    return AuthorityTier.AI_SUMMARY
