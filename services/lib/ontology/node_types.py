"""Enum of all node types recognized by LexGraph.

Adding a type here is the first step to extending the ontology; you must also
update:
  - authority.py  (if it carries a tier)
  - rules.py      (if it has structural constraints)
  - enrichment/   (if something must produce it)
  - docs/ontology.md
"""

from __future__ import annotations

from enum import StrEnum


class NodeType(StrEnum):
    # --- public law ---
    CONSTITUTION = "Constitution"
    ACT = "Act"
    AMENDMENT = "Amendment"
    PART = "Part"
    CHAPTER = "Chapter"
    SECTION = "Section"
    SUBSECTION = "Subsection"
    PROVISO = "Proviso"
    EXPLANATION = "Explanation"
    ILLUSTRATION = "Illustration"
    RULE = "Rule"
    REGULATION = "Regulation"
    NOTIFICATION = "Notification"
    CIRCULAR = "Circular"
    SCHEDULE = "Schedule"

    # --- judicial ---
    CASE = "Case"
    COURT = "Court"
    BENCH = "Bench"
    JUDGE = "Judge"
    PARTY = "Party"
    CITATION = "Citation"
    PARAGRAPH = "Paragraph"
    HOLDING = "Holding"
    RATIO = "Ratio"
    OBITER = "Obiter"
    ISSUE = "Issue"
    LEGAL_TEST = "LegalTest"
    DOCTRINE = "Doctrine"
    PRECEDENT = "Precedent"
    PROCEDURAL_STAGE = "ProceduralStage"
    RELIEF = "Relief"
    OUTCOME = "Outcome"

    # --- offence / procedure / evidence ---
    OFFENCE = "Offence"
    INGREDIENT = "Ingredient"
    PUNISHMENT = "Punishment"
    PROCEDURE = "Procedure"
    REQUIREMENT = "Requirement"
    STANDARD_OF_PROOF = "StandardOfProof"
    EVIDENCE_RULE = "EvidenceRule"
    EVIDENTIARY_ISSUE = "EvidentiaryIssue"

    # --- private case material ---
    MATTER = "Matter"
    DOCUMENT = "Document"
    WITNESS = "Witness"
    STATEMENT = "Statement"
    EXHIBIT = "Exhibit"
    FACT = "Fact"
    TIMELINE_EVENT = "TimelineEvent"
    ALLEGATION = "Allegation"
    DEFENSE = "Defense"
    ARGUMENT = "Argument"
    CONTRADICTION = "Contradiction"
    MEDICAL_RECORD = "MedicalRecord"
    FORENSIC_RECORD = "ForensicRecord"
    NOTICE = "Notice"
    CONTRACT_CLAUSE = "ContractClause"
    COMMUNICATION = "Communication"

    # --- system / provenance ---
    SOURCE_EPISODE = "SourceEpisode"
    SOURCE_SPAN = "SourceSpan"
    FILE = "File"
    CHUNK = "Chunk"
    EXTRACTED_CLAIM = "ExtractedClaim"
    SUMMARY_NODE = "SummaryNode"
    CROSSWALK = "Crosswalk"
    JURISDICTION = "Jurisdiction"
    VALIDITY_PERIOD = "ValidityPeriod"


NODE_TYPES: frozenset[NodeType] = frozenset(NodeType)
