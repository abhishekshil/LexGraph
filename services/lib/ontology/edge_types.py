"""Canonical edge types. Every edge stored in the graph MUST be one of these."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .node_types import NodeType


class EdgeType(StrEnum):
    # --- structural (statute) ---
    ACT_CONTAINS_PART = "ACT_CONTAINS_PART"
    ACT_CONTAINS_CHAPTER = "ACT_CONTAINS_CHAPTER"
    CHAPTER_CONTAINS_SECTION = "CHAPTER_CONTAINS_SECTION"
    SECTION_CONTAINS_SUBSECTION = "SECTION_CONTAINS_SUBSECTION"
    SECTION_HAS_PROVISO = "SECTION_HAS_PROVISO"
    SECTION_HAS_EXPLANATION = "SECTION_HAS_EXPLANATION"
    SECTION_HAS_ILLUSTRATION = "SECTION_HAS_ILLUSTRATION"
    ACT_HAS_SCHEDULE = "ACT_HAS_SCHEDULE"

    # --- temporal / amendment / crosswalk ---
    SECTION_AMENDED_BY = "SECTION_AMENDED_BY"
    SECTION_REPEALED_BY = "SECTION_REPEALED_BY"
    SECTION_CROSSWALK_TO = "SECTION_CROSSWALK_TO"
    NODE_HAS_VALIDITY = "NODE_HAS_VALIDITY"

    # --- judicial ---
    CASE_CITES_CASE = "CASE_CITES_CASE"
    CASE_DISTINGUISHES_CASE = "CASE_DISTINGUISHES_CASE"
    CASE_FOLLOWS_CASE = "CASE_FOLLOWS_CASE"
    CASE_OVERRULES_CASE = "CASE_OVERRULES_CASE"
    CASE_INTERPRETS_SECTION = "CASE_INTERPRETS_SECTION"
    CASE_APPLIES_STATUTE = "CASE_APPLIES_STATUTE"
    CASE_REFERENCES_DOCTRINE = "CASE_REFERENCES_DOCTRINE"
    PARAGRAPH_SUPPORTS_HOLDING = "PARAGRAPH_SUPPORTS_HOLDING"
    HOLDING_RESOLVES_ISSUE = "HOLDING_RESOLVES_ISSUE"
    ISSUE_INVOLVES_DOCTRINE = "ISSUE_INVOLVES_DOCTRINE"

    # --- offence / procedure / evidence ---
    OFFENCE_HAS_INGREDIENT = "OFFENCE_HAS_INGREDIENT"
    SECTION_PRESCRIBES_PUNISHMENT = "SECTION_PRESCRIBES_PUNISHMENT"
    PROCEDURE_GOVERNED_BY_SECTION = "PROCEDURE_GOVERNED_BY_SECTION"
    EVIDENCE_RULE_GOVERNED_BY_SECTION = "EVIDENCE_RULE_GOVERNED_BY_SECTION"

    # --- private case material ---
    DOCUMENT_BELONGS_TO_MATTER = "DOCUMENT_BELONGS_TO_MATTER"
    DOCUMENT_HAS_CONFIDENTIALITY = "DOCUMENT_HAS_CONFIDENTIALITY"
    DOCUMENT_CONTAINS_FACT = "DOCUMENT_CONTAINS_FACT"
    WITNESS_STATES_FACT = "WITNESS_STATES_FACT"
    EXHIBIT_SUPPORTS_FACT = "EXHIBIT_SUPPORTS_FACT"
    EXHIBIT_CONTRADICTS_FACT = "EXHIBIT_CONTRADICTS_FACT"
    FACT_RELEVANT_TO_ISSUE = "FACT_RELEVANT_TO_ISSUE"
    FACT_LINKED_TO_OFFENCE = "FACT_LINKED_TO_OFFENCE"
    FACT_LINKED_TO_INGREDIENT = "FACT_LINKED_TO_INGREDIENT"
    FACT_OCCURS_AT_TIME = "FACT_OCCURS_AT_TIME"
    ARGUMENT_SUPPORTS_POSITION = "ARGUMENT_SUPPORTS_POSITION"
    ARGUMENT_CONTRADICTS_ARGUMENT = "ARGUMENT_CONTRADICTS_ARGUMENT"

    # --- provenance / derived ---
    SOURCE_SPAN_SUPPORTS_CLAIM = "SOURCE_SPAN_SUPPORTS_CLAIM"
    CLAIM_TRACED_TO_EPISODE = "CLAIM_TRACED_TO_EPISODE"
    NODE_DERIVED_FROM_SOURCE = "NODE_DERIVED_FROM_SOURCE"
    NODE_SUMMARIZES_NEIGHBORHOOD = "NODE_SUMMARIZES_NEIGHBORHOOD"


@dataclass(frozen=True)
class EdgeSchema:
    """Allowed endpoints + whether the edge is temporally validated."""

    kind: EdgeType
    src: tuple[NodeType, ...]
    dst: tuple[NodeType, ...]
    temporal: bool = False

    def permits(self, src_type: NodeType, dst_type: NodeType) -> bool:
        return src_type in self.src and dst_type in self.dst


# Pairs declared here are the only legal edge endpoints. Retrieval planners can
# trust these signatures to prune traversal.
EDGE_SCHEMAS: dict[EdgeType, EdgeSchema] = {
    EdgeType.ACT_CONTAINS_PART: EdgeSchema(
        EdgeType.ACT_CONTAINS_PART, (NodeType.ACT,), (NodeType.PART,)
    ),
    EdgeType.ACT_CONTAINS_CHAPTER: EdgeSchema(
        EdgeType.ACT_CONTAINS_CHAPTER, (NodeType.ACT, NodeType.PART), (NodeType.CHAPTER,)
    ),
    EdgeType.CHAPTER_CONTAINS_SECTION: EdgeSchema(
        EdgeType.CHAPTER_CONTAINS_SECTION,
        (NodeType.CHAPTER, NodeType.PART, NodeType.ACT),
        (NodeType.SECTION,),
    ),
    EdgeType.SECTION_CONTAINS_SUBSECTION: EdgeSchema(
        EdgeType.SECTION_CONTAINS_SUBSECTION, (NodeType.SECTION,), (NodeType.SUBSECTION,)
    ),
    EdgeType.SECTION_HAS_PROVISO: EdgeSchema(
        EdgeType.SECTION_HAS_PROVISO,
        (NodeType.SECTION, NodeType.SUBSECTION),
        (NodeType.PROVISO,),
    ),
    EdgeType.SECTION_HAS_EXPLANATION: EdgeSchema(
        EdgeType.SECTION_HAS_EXPLANATION,
        (NodeType.SECTION, NodeType.SUBSECTION),
        (NodeType.EXPLANATION,),
    ),
    EdgeType.SECTION_HAS_ILLUSTRATION: EdgeSchema(
        EdgeType.SECTION_HAS_ILLUSTRATION,
        (NodeType.SECTION, NodeType.SUBSECTION),
        (NodeType.ILLUSTRATION,),
    ),
    EdgeType.ACT_HAS_SCHEDULE: EdgeSchema(
        EdgeType.ACT_HAS_SCHEDULE, (NodeType.ACT,), (NodeType.SCHEDULE,)
    ),
    EdgeType.SECTION_AMENDED_BY: EdgeSchema(
        EdgeType.SECTION_AMENDED_BY,
        (NodeType.SECTION, NodeType.SUBSECTION),
        (NodeType.AMENDMENT,),
        temporal=True,
    ),
    EdgeType.SECTION_REPEALED_BY: EdgeSchema(
        EdgeType.SECTION_REPEALED_BY,
        (NodeType.SECTION, NodeType.SUBSECTION, NodeType.ACT),
        (NodeType.AMENDMENT, NodeType.ACT),
        temporal=True,
    ),
    EdgeType.SECTION_CROSSWALK_TO: EdgeSchema(
        EdgeType.SECTION_CROSSWALK_TO,
        (NodeType.SECTION,),
        (NodeType.SECTION,),
        temporal=True,
    ),
    EdgeType.NODE_HAS_VALIDITY: EdgeSchema(
        EdgeType.NODE_HAS_VALIDITY,
        tuple(NodeType),  # any node can be temporal
        (NodeType.VALIDITY_PERIOD,),
        temporal=True,
    ),
    EdgeType.CASE_CITES_CASE: EdgeSchema(
        EdgeType.CASE_CITES_CASE, (NodeType.CASE,), (NodeType.CASE,)
    ),
    EdgeType.CASE_DISTINGUISHES_CASE: EdgeSchema(
        EdgeType.CASE_DISTINGUISHES_CASE, (NodeType.CASE,), (NodeType.CASE,)
    ),
    EdgeType.CASE_FOLLOWS_CASE: EdgeSchema(
        EdgeType.CASE_FOLLOWS_CASE, (NodeType.CASE,), (NodeType.CASE,)
    ),
    EdgeType.CASE_OVERRULES_CASE: EdgeSchema(
        EdgeType.CASE_OVERRULES_CASE, (NodeType.CASE,), (NodeType.CASE,)
    ),
    EdgeType.CASE_INTERPRETS_SECTION: EdgeSchema(
        EdgeType.CASE_INTERPRETS_SECTION,
        (NodeType.CASE, NodeType.PARAGRAPH, NodeType.HOLDING),
        (NodeType.SECTION, NodeType.SUBSECTION, NodeType.PROVISO),
    ),
    EdgeType.CASE_APPLIES_STATUTE: EdgeSchema(
        EdgeType.CASE_APPLIES_STATUTE, (NodeType.CASE,), (NodeType.ACT,)
    ),
    EdgeType.CASE_REFERENCES_DOCTRINE: EdgeSchema(
        EdgeType.CASE_REFERENCES_DOCTRINE, (NodeType.CASE,), (NodeType.DOCTRINE,)
    ),
    EdgeType.PARAGRAPH_SUPPORTS_HOLDING: EdgeSchema(
        EdgeType.PARAGRAPH_SUPPORTS_HOLDING, (NodeType.PARAGRAPH,), (NodeType.HOLDING,)
    ),
    EdgeType.HOLDING_RESOLVES_ISSUE: EdgeSchema(
        EdgeType.HOLDING_RESOLVES_ISSUE, (NodeType.HOLDING,), (NodeType.ISSUE,)
    ),
    EdgeType.ISSUE_INVOLVES_DOCTRINE: EdgeSchema(
        EdgeType.ISSUE_INVOLVES_DOCTRINE, (NodeType.ISSUE,), (NodeType.DOCTRINE,)
    ),
    EdgeType.OFFENCE_HAS_INGREDIENT: EdgeSchema(
        EdgeType.OFFENCE_HAS_INGREDIENT, (NodeType.OFFENCE,), (NodeType.INGREDIENT,)
    ),
    EdgeType.SECTION_PRESCRIBES_PUNISHMENT: EdgeSchema(
        EdgeType.SECTION_PRESCRIBES_PUNISHMENT,
        (NodeType.SECTION, NodeType.SUBSECTION),
        (NodeType.PUNISHMENT,),
    ),
    EdgeType.PROCEDURE_GOVERNED_BY_SECTION: EdgeSchema(
        EdgeType.PROCEDURE_GOVERNED_BY_SECTION,
        (NodeType.PROCEDURE,),
        (NodeType.SECTION, NodeType.SUBSECTION),
    ),
    EdgeType.EVIDENCE_RULE_GOVERNED_BY_SECTION: EdgeSchema(
        EdgeType.EVIDENCE_RULE_GOVERNED_BY_SECTION,
        (NodeType.EVIDENCE_RULE,),
        (NodeType.SECTION, NodeType.SUBSECTION),
    ),
    EdgeType.DOCUMENT_BELONGS_TO_MATTER: EdgeSchema(
        EdgeType.DOCUMENT_BELONGS_TO_MATTER, (NodeType.DOCUMENT,), (NodeType.MATTER,)
    ),
    EdgeType.DOCUMENT_HAS_CONFIDENTIALITY: EdgeSchema(
        EdgeType.DOCUMENT_HAS_CONFIDENTIALITY,
        (NodeType.DOCUMENT,),
        (NodeType.DOCUMENT,),  # materialized as a property; kept for audit edges
    ),
    EdgeType.DOCUMENT_CONTAINS_FACT: EdgeSchema(
        EdgeType.DOCUMENT_CONTAINS_FACT, (NodeType.DOCUMENT,), (NodeType.FACT,)
    ),
    EdgeType.WITNESS_STATES_FACT: EdgeSchema(
        EdgeType.WITNESS_STATES_FACT,
        (NodeType.WITNESS, NodeType.STATEMENT),
        (NodeType.FACT,),
    ),
    EdgeType.EXHIBIT_SUPPORTS_FACT: EdgeSchema(
        EdgeType.EXHIBIT_SUPPORTS_FACT, (NodeType.EXHIBIT,), (NodeType.FACT,)
    ),
    EdgeType.EXHIBIT_CONTRADICTS_FACT: EdgeSchema(
        EdgeType.EXHIBIT_CONTRADICTS_FACT, (NodeType.EXHIBIT,), (NodeType.FACT,)
    ),
    EdgeType.FACT_RELEVANT_TO_ISSUE: EdgeSchema(
        EdgeType.FACT_RELEVANT_TO_ISSUE,
        (NodeType.FACT,),
        (NodeType.ISSUE, NodeType.INGREDIENT),
    ),
    EdgeType.FACT_LINKED_TO_OFFENCE: EdgeSchema(
        EdgeType.FACT_LINKED_TO_OFFENCE, (NodeType.FACT,), (NodeType.OFFENCE,)
    ),
    EdgeType.FACT_LINKED_TO_INGREDIENT: EdgeSchema(
        EdgeType.FACT_LINKED_TO_INGREDIENT, (NodeType.FACT,), (NodeType.INGREDIENT,)
    ),
    EdgeType.FACT_OCCURS_AT_TIME: EdgeSchema(
        EdgeType.FACT_OCCURS_AT_TIME, (NodeType.FACT,), (NodeType.TIMELINE_EVENT,)
    ),
    EdgeType.ARGUMENT_SUPPORTS_POSITION: EdgeSchema(
        EdgeType.ARGUMENT_SUPPORTS_POSITION,
        (NodeType.ARGUMENT,),
        (NodeType.ISSUE, NodeType.ALLEGATION, NodeType.DEFENSE),
    ),
    EdgeType.ARGUMENT_CONTRADICTS_ARGUMENT: EdgeSchema(
        EdgeType.ARGUMENT_CONTRADICTS_ARGUMENT, (NodeType.ARGUMENT,), (NodeType.ARGUMENT,)
    ),
    EdgeType.SOURCE_SPAN_SUPPORTS_CLAIM: EdgeSchema(
        EdgeType.SOURCE_SPAN_SUPPORTS_CLAIM,
        (NodeType.SOURCE_SPAN,),
        (NodeType.EXTRACTED_CLAIM,),
    ),
    EdgeType.CLAIM_TRACED_TO_EPISODE: EdgeSchema(
        EdgeType.CLAIM_TRACED_TO_EPISODE,
        (NodeType.EXTRACTED_CLAIM,),
        (NodeType.SOURCE_EPISODE,),
    ),
    EdgeType.NODE_DERIVED_FROM_SOURCE: EdgeSchema(
        EdgeType.NODE_DERIVED_FROM_SOURCE,
        tuple(NodeType),
        (NodeType.SOURCE_SPAN, NodeType.SOURCE_EPISODE),
    ),
    EdgeType.NODE_SUMMARIZES_NEIGHBORHOOD: EdgeSchema(
        EdgeType.NODE_SUMMARIZES_NEIGHBORHOOD,
        (NodeType.SUMMARY_NODE,),
        tuple(NodeType),
    ),
}


EDGE_TYPES: frozenset[EdgeType] = frozenset(EdgeType)
