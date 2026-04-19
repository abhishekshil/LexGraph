"""Grounded generator.

Flow::

    EvidencePack
        │
        ├─ refusal if pack.insufficient_evidence or no spans
        │
        ▼
    provider.complete(question, pack_text)
        │
        ▼
    enforce() — strip fabricated markers, drop unsupported claims
        │
        ▼
    Answer (with citations resolved back to nodes)

The enforcer is the last line of defence: even if the LLM hallucinates, its
output cannot leak past this gate without a real span citation.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from ..core import get_logger
from ..data_models.answer import Answer, AnswerCitation, AnswerConflict, GraphPath
from ..data_models.evidence import EvidencePack, EvidenceSpan
from ..observability import emit_step
from .enforce import EnforcementReport, enforce, format_answer
from .providers import LLMProvider, StubProvider, get_provider


log = get_logger("generation")


class GroundedGenerator:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_provider()

    async def generate(self, pack: EvidencePack, *, trace_id: str) -> Answer:
        if pack.insufficient_evidence or not pack.spans:
            await emit_step(
                "generation.refuse",
                status="warn",
                worker="generate",
                message="Refusing — insufficient evidence",
                reason="retrieval_insufficient",
                spans=len(pack.spans),
            )
            return _refusal(pack, trace_id, reason="retrieval_insufficient")

        pack_text = _format_pack(pack)
        await emit_step(
            "generation.llm",
            status="start",
            worker="generate",
            message=f"Calling LLM provider ({getattr(self.provider, 'name', '?')})",
            provider=getattr(self.provider, "name", "?"),
            pack_chars=len(pack_text),
            spans=len(pack.spans),
        )
        raw = await self._complete_safely(pack_text, pack.query)
        await emit_step(
            "generation.llm",
            status="done",
            worker="generate",
            message=f"LLM returned {len(raw)} chars",
            chars=len(raw),
        )
        await emit_step(
            "generation.enforce",
            status="start",
            worker="generate",
            message="Enforcing citation-only output (stripping unsupported claims)",
        )
        clean, report = enforce(raw, pack)
        await emit_step(
            "generation.enforce",
            status="done",
            worker="generate",
            message=(
                f"kept {len(clean.used_markers)} marker(s); "
                f"dropped {len(report.dropped_sentences)}; "
                f"fabricated {len(report.fabricated_markers)}"
            ),
            used_markers=sorted(clean.used_markers),
            dropped=len(report.dropped_sentences),
            fabricated=sorted(report.fabricated_markers),
            confidence=clean.confidence,
        )

        # If every claim was dropped or the enforcer declared the output
        # unsupported, surface a refusal instead of an empty answer.
        if not clean.answer.strip() or not clean.used_markers:
            log.warning(
                "generation.refused_after_enforcement",
                dropped=len(report.dropped_sentences),
                fabricated=len(report.fabricated_markers),
            )
            await emit_step(
                "generation.refuse",
                status="warn",
                worker="generate",
                message="Refusing — enforcement stripped all claims",
                reason="enforcement_empty",
            )
            return _refusal(pack, trace_id, reason="enforcement_empty")

        rendered = format_answer(clean)

        legal_basis, private = _resolve_citations(rendered, pack)
        answer = Answer(
            question=pack.query,
            query_type=pack.query_type,
            answer=rendered,
            legal_basis=legal_basis,
            supporting_private_sources=private,
            graph_paths=_graph_paths(pack),
            conflicts=_conflicts(pack.conflicts),
            confidence=clean.confidence,
            insufficient_evidence=clean.insufficient,
            trace_id=trace_id,
            evidence_pack_id=f"pack_{uuid4().hex}",
            notes=_build_notes(report, provider=self.provider),
            extras={
                "provider": getattr(self.provider, "name", "unknown"),
                "enforcement": {
                    "dropped": len(report.dropped_sentences),
                    "fabricated_markers": sorted(report.fabricated_markers),
                    "rejection_rate": report.rejection_rate,
                },
            },
        )
        log.info(
            "generation.done",
            provider=getattr(self.provider, "name", "?"),
            confidence=answer.confidence,
            insufficient=answer.insufficient_evidence,
            citations=len(answer.legal_basis),
            private=len(answer.supporting_private_sources),
        )
        return answer

    async def _complete_safely(self, pack_text: str, question: str) -> str:
        """Call the provider; on *any* error fall back to the stub provider
        so the generation agent never crashes a query."""
        try:
            return await self.provider.complete(
                question=question, evidence_pack_text=pack_text
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "generation.provider_failed",
                provider=getattr(self.provider, "name", "?"),
                error=str(e),
            )
            return await StubProvider().complete(
                question=question, evidence_pack_text=pack_text
            )


# ---------------------------------------------------------------------------
# Pack formatting
# ---------------------------------------------------------------------------


def _format_pack(pack: EvidencePack) -> str:
    lines: list[str] = []
    for s in pack.spans:
        header = _header_for(s)
        lines.append(header)
        lines.append(s.excerpt.strip())
        lines.append("---")
    if pack.conflicts:
        lines.append("Conflicts:")
        for c in pack.conflicts:
            markers = ", ".join(c.get("markers") or [])
            lines.append(f"- {c.get('description', 'conflict')}  (markers: {markers})")
    return "\n".join(lines)


def _header_for(s: EvidenceSpan) -> str:
    parts = [f"[{s.marker}] tier={int(s.tier)} kind={s.kind}"]
    for label in (s.title, s.section_or_paragraph, s.citation, s.court, s.date):
        if label:
            parts.append(str(label))
    return " | ".join(parts)


# ---------------------------------------------------------------------------
# Citation resolution
# ---------------------------------------------------------------------------


def _resolve_citations(
    text: str, pack: EvidencePack
) -> tuple[list[AnswerCitation], list[AnswerCitation]]:
    import re

    used = {f"S{n}" for n in re.findall(r"\[S(\d+)\]", text)}
    by_marker = {s.marker: s for s in pack.spans}
    public: list[AnswerCitation] = []
    private: list[AnswerCitation] = []
    for marker in sorted(used, key=lambda m: int(m[1:])):
        s = by_marker.get(marker)
        if not s:
            continue
        cit = AnswerCitation(
            marker=marker,
            type=_citation_type(s.node_type, s.kind),
            title=s.title,
            authority=_authority_for(s),
            court=s.court,
            date=s.date,
            section_or_paragraph=s.section_or_paragraph,
            excerpt=s.excerpt,
            source_id=s.source_episode_id,
            source_span_id=s.source_span_id,
            file_id=s.file_id,
            node_id=s.node_id,
            tier=s.tier,
            score=s.score,
        )
        (private if s.kind == "private" else public).append(cit)
    return public, private


def _citation_type(node_type: str, kind: str) -> str:
    if kind == "private":
        return "private_document"
    nt = (node_type or "").lower()
    if any(k in nt for k in ("act", "section", "chapter", "proviso", "schedule")):
        return "statute"
    if "notification" in nt:
        return "notification"
    if "regulation" in nt:
        return "regulation"
    if "rule" in nt:
        return "rule"
    if "summary" in nt or "extracted" in nt:
        return "summary"
    return "judgment"


def _authority_for(s: EvidenceSpan) -> str | None:
    if s.court:
        return s.court
    if s.kind == "public" and int(s.tier) == 1:
        return "Government of India"
    return None


# ---------------------------------------------------------------------------
# Conflicts + graph paths
# ---------------------------------------------------------------------------


def _conflicts(conflicts: list[dict[str, Any]]) -> list[AnswerConflict]:
    out: list[AnswerConflict] = []
    for c in conflicts or []:
        tiers = c.get("tiers") or []
        severity = "high" if tiers and min(tiers) == 1 else "medium"
        out.append(
            AnswerConflict(
                description=c.get("description", "conflict"),
                citations=list(c.get("markers") or []),
                severity=severity,
            )
        )
    return out


def _graph_paths(pack: EvidencePack) -> list[GraphPath]:
    paths: list[GraphPath] = []
    for p in pack.graph_paths:
        if not p:
            continue
        nodes = [x for i, x in enumerate(p) if i % 2 == 0]
        edges = [x for i, x in enumerate(p) if i % 2 == 1]
        paths.append(
            GraphPath(nodes=nodes, edges=edges, narrative=" → ".join(map(str, p)))
        )
    return paths


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def _refusal(pack: EvidencePack, trace_id: str, *, reason: str) -> Answer:
    msg = (
        "Answer: Insufficient evidence was retrieved to answer this question "
        "from authoritative sources. No claim has been made. "
        "Narrow the query, add more relevant material, or check the "
        "ingestion status.\n\n"
        "Legal basis:\n"
        "Confidence: LOW\n"
        "Insufficient evidence: YES"
    )
    return Answer(
        question=pack.query,
        query_type=pack.query_type,
        answer=msg,
        legal_basis=[],
        confidence="low",
        insufficient_evidence=True,
        trace_id=trace_id,
        evidence_pack_id=f"pack_{uuid4().hex}",
        notes=[f"refusal:{reason}"],
        extras={"refusal_reason": reason},
    )


def _build_notes(
    report: EnforcementReport, *, provider: LLMProvider
) -> list[str]:
    notes: list[str] = [f"provider:{getattr(provider, 'name', 'unknown')}"]
    if report.dropped_sentences:
        notes.append(f"enforcement_dropped:{len(report.dropped_sentences)}")
    if report.fabricated_markers:
        notes.append(
            "enforcement_fabricated:" + ",".join(sorted(report.fabricated_markers))
        )
    return notes
