"""Typed metadata for different kinds of ingested documents."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class DocumentKind(StrEnum):
    # public
    STATUTE = "statute"
    AMENDMENT_ACT = "amendment_act"
    RULE_SET = "rule_set"
    REGULATION = "regulation"
    NOTIFICATION = "notification"
    CIRCULAR = "circular"
    JUDGMENT = "judgment"
    ORDER = "order"
    # private
    PLAINT = "plaint"
    WRITTEN_STATEMENT = "written_statement"
    REJOINDER = "rejoinder"
    AFFIDAVIT = "affidavit"
    WITNESS_STATEMENT = "witness_statement"
    FIR = "fir"
    COMPLAINT = "complaint"
    CHARGESHEET = "chargesheet"
    REMAND_PAPER = "remand_paper"
    EXHIBIT = "exhibit"
    CONTRACT = "contract"
    NOTICE = "notice"
    CORRESPONDENCE = "correspondence"
    EMAIL = "email"
    TIMELINE = "timeline"
    NOTE = "note"
    MEMO = "memo"
    MEDICAL_RECORD = "medical_record"
    FORENSIC_RECORD = "forensic_record"
    GENERIC = "generic"


Confidentiality = Literal["public", "client_privileged", "private", "restricted"]


class DocumentMetadata(BaseModel):
    """Baseline metadata for every ingested document."""

    title: str | None = None
    filename: str
    source_id: str | None = None
    matter_id: str | None = None
    kind: DocumentKind = DocumentKind.GENERIC
    confidentiality: Confidentiality = "public"
    jurisdiction: str | None = None
    validity_start: date | None = None
    validity_end: date | None = None
    document_hash: str | None = None
    version_id: str | None = None


class StatuteMetadata(DocumentMetadata):
    """Extra fields when we know this is a statute / amendment / rule."""

    act_name: str | None = None
    act_number: str | None = None
    year: int | None = None
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    proviso: str | None = None
    explanation: str | None = None
    rule_number: str | None = None
    regulation_number: str | None = None
    notification_number: str | None = None


class JudgmentMetadata(DocumentMetadata):
    court: str | None = None
    bench: str | None = None
    judge_names: list[str] = Field(default_factory=list)
    parties: list[str] = Field(default_factory=list)
    citation: str | None = None
    case_number: str | None = None
    decision_date: date | None = None
    filing_date: date | None = None


class PrivateDocMetadata(DocumentMetadata):
    matter_id: str
    exhibit_id: str | None = None
    witness_name: str | None = None
    page_number: int | None = None
    paragraph_number: int | None = None
