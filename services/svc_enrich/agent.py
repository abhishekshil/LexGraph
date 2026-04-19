"""EnrichAgent: legal NER + citation + section-ref extraction per span.

Produces typed node+edge payloads without touching the graph directly. The
GraphWriterAgent is the only component allowed to mutate the graph, so the
writer can enforce ontology invariants in one place.
"""

from __future__ import annotations

from typing import Any

from services.lib.bus.factory import Streams
from services.lib.core import settings
from services.lib.data_models.events import (
    EnrichCompletedEvent,
    Event,
    SegmentCompletedEvent,
)
from services.lib.enrichment import (
    CitationExtractor,
    LegalNER,
    TransformerLegalNER,
    extract_section_refs,
)
from services.lib.enrichment.crosswalk_loader import load_all_crosswalks
from services.agent_base import Agent


class EnrichAgent(Agent):
    name = "enrich"
    listens = (Streams.SEGMENT_COMPLETED,)
    publishes = (Streams.ENRICH_COMPLETED,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Wire up an optional transformer NER layer. It stays silent and
        # returns [] if the model isn't configured or fails to load, so the
        # regex baseline remains authoritative.
        transformer: TransformerLegalNER | None = None
        if settings.enrich_ner_enabled and settings.enrich_ner_model:
            transformer = TransformerLegalNER(
                model_name=settings.enrich_ner_model,
                enabled=True,
            )
        self.ner = LegalNER(transformer=transformer)
        self.citer = CitationExtractor()
        self.crosswalks = load_all_crosswalks()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, SegmentCompletedEvent):
            return

        nodes: list[dict[str, Any]] = []
        edges: list[dict[str, Any]] = []

        for span in event.spans:
            seg_nt = span.extra.get("seg_node_type") or "Document"
            seg_label = span.extra.get("seg_label") or "unknown"
            seg_parent = span.extra.get("seg_parent_label")

            # Prefer the segmenter's canonical id (e.g. "section:ipc:378") so
            # multiple ingests collapse onto the same node and crosswalk edges
            # can target real nodes. Fall back to episode-scoped ids for units
            # that are inherently case-specific (Paragraph / Witness / Fact).
            canonical = span.extra.get("canonical_id")
            node_id = canonical or f"{seg_nt.lower()}:{event.episode_id}:{span.id}"
            node_props: dict[str, Any] = {
                "label": seg_label,
                "text": span.text[:2000],
                "page": span.page,
                "matter_id": span.matter_id,
            }
            # Required props for statute-ish nodes
            if seg_nt == "Section":
                act_ref = span.extra.get("act_ref") or span.extra.get("act_token") or ""
                node_props.update(
                    {
                        "number": span.extra.get("number", seg_label.split(" ")[-1]),
                        "act_ref": act_ref or f"episode:{event.episode_id}",
                        "heading": span.extra.get("heading", ""),
                    }
                )
            if seg_nt == "Act":
                node_props.update(
                    {
                        "short_title": span.extra.get("short_title") or seg_label,
                        "year": span.extra.get("year", ""),
                        "jurisdiction": span.extra.get("jurisdiction", "IN"),
                    }
                )
            if seg_nt == "Subsection":
                node_props.update(
                    {
                        "number": span.extra.get("number", ""),
                        "section_ref": seg_parent,
                    }
                )
            if seg_nt in {"Proviso", "Explanation", "Illustration"}:
                node_props["parent_ref"] = seg_parent
            if seg_nt == "Paragraph":
                node_props.update(
                    {
                        "number": span.extra.get("number", seg_label.split(" ")[-1]),
                        "case_ref": span.extra.get("case_ref")
                        or f"episode:{event.episode_id}",
                    }
                )
            if seg_nt == "Witness":
                node_props.update(
                    {
                        "name": span.extra.get("name") or seg_label,
                        "matter_ref": span.matter_id or "unknown_matter",
                    }
                )
            if seg_nt == "Exhibit":
                node_props.update(
                    {
                        "label": span.extra.get("exhibit_label") or seg_label,
                        "document_ref": span.extra.get("document_ref")
                        or f"episode:{event.episode_id}",
                    }
                )
            if seg_nt == "Document":
                node_props.update(
                    {
                        "matter_ref": span.matter_id or "public",
                        "filename": span.extra.get("filename", seg_label),
                        "kind": span.extra.get("doc_kind", "generic"),
                    }
                )

            nodes.append(
                {
                    "node_type": seg_nt,
                    "node_id": node_id,
                    "props": node_props,
                    "provenance_span_id": span.id,
                    "register_as_graphiti_episode": seg_nt in {"Section", "Paragraph", "Exhibit", "Statement"},
                }
            )
            # NODE_DERIVED_FROM_SOURCE is added by the writer automatically.

            # Entities found in the span.
            for ent in self.ner.extract(span.text):
                ent_node_id = f"{ent.type.lower()}:{_slug(ent.text)}"
                nodes.append(
                    {
                        "node_type": ent.type,
                        "node_id": ent_node_id,
                        "props": {"name": ent.text, **ent.extra,
                                  "level": ent.extra.get("level")},
                        "provenance_span_id": span.id,
                    }
                )

            # Section references → edges (CASE_INTERPRETS_SECTION if this span
            # is a judgment paragraph; FACT_LINKED_TO_INGREDIENT not inferable
            # here so left to a later LLM pass).
            for ref in extract_section_refs(span.text):
                tgt_section_id = f"section:{_slug(ref.act)}:{(ref.section or '').lower()}"
                if seg_nt == "Paragraph":
                    edges.append(
                        {
                            "edge_type": "CASE_INTERPRETS_SECTION",
                            "src_type": "Paragraph",
                            "src_id": node_id,
                            "dst_type": "Section",
                            "dst_id": tgt_section_id,
                        }
                    )

            # Citations → CASE_CITES_CASE edges (only if this span belongs to a
            # Paragraph; the graph writer will resolve target Case node on
            # demand). We key the dst_id on `canonical_id`, which is stable
            # across different reporter formats for the same case — so every
            # re-citation collapses to one Case node.
            for cit in self.citer.extract(span.text):
                if seg_nt != "Paragraph":
                    continue
                if cit.kind not in {"neutral", "reporter", "case_title", "combined"}:
                    continue
                edge_props: dict[str, Any] = {
                    "as_of": "",
                    "raw": cit.raw,
                    "reporter": cit.reporter or "",
                    "court": cit.court,
                    "year": cit.year or 0,
                }
                if cit.parties:
                    edge_props["petitioner"] = cit.parties[0]
                    edge_props["respondent"] = cit.parties[1]
                edges.append(
                    {
                        "edge_type": "CASE_CITES_CASE",
                        "src_type": "Paragraph",
                        "src_id": node_id,
                        "dst_type": "Case",
                        "dst_id": cit.canonical_id,
                        "props": edge_props,
                    }
                )

        # Crosswalk edges. Only emit those where at least one endpoint matches
        # a section we just wrote — otherwise we spray phantom Section nodes
        # across the graph with no provenance. A bootstrap job (scripts/
        # seed_crosswalks.py) can materialise the full crosswalk closure once
        # the canonical statutes have been loaded.
        section_ids = {n["node_id"] for n in nodes if n["node_type"] == "Section"}
        for cw in self.crosswalks.values():
            src_act_tok = _slug(cw.source_act)
            tgt_act_tok = _slug(cw.target_act)
            # Re-map full act slugs onto canonical tokens the segmenter uses.
            src_act_tok = _ACT_SLUG_TO_TOKEN.get(src_act_tok, src_act_tok)
            tgt_act_tok = _ACT_SLUG_TO_TOKEN.get(tgt_act_tok, tgt_act_tok)
            for entry in cw.entries:
                src_id = f"section:{src_act_tok}:{entry.source_section.lower()}"
                dst_id = f"section:{tgt_act_tok}:{entry.target_section.lower()}"
                if src_id not in section_ids and dst_id not in section_ids:
                    continue
                edges.append(
                    {
                        "edge_type": "SECTION_CROSSWALK_TO",
                        "src_type": "Section",
                        "src_id": src_id,
                        "dst_type": "Section",
                        "dst_id": dst_id,
                        "props": {
                            "mapping_type": entry.mapping_type,
                            "topic": entry.topic or "",
                            "notes": entry.notes or "",
                            "as_of": cw.version,
                        },
                    }
                )

        out = EnrichCompletedEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            episode_id=event.episode_id,
            nodes=nodes,
            edges=edges,
        )
        await self.bus.publish(Streams.ENRICH_COMPLETED, out)
        self.log.info(
            "enrich.done",
            episode_id=event.episode_id,
            nodes=len(nodes),
            edges=len(edges),
        )


def _slug(s: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "unknown"


# Keep crosswalk edge ids aligned with the canonical ids the statute segmenter
# emits (e.g. "section:ipc:378"). The crosswalk YAMLs use prose act names, so
# we translate those into the short canonical tokens.
_ACT_SLUG_TO_TOKEN: dict[str, str] = {
    "indian_penal_code_1860": "ipc",
    "indian_penal_code": "ipc",
    "bharatiya_nyaya_sanhita_2023": "bns",
    "bharatiya_nyaya_sanhita": "bns",
    "code_of_criminal_procedure_1973": "crpc",
    "code_of_criminal_procedure": "crpc",
    "bharatiya_nagarik_suraksha_sanhita_2023": "bnss",
    "bharatiya_nagarik_suraksha_sanhita": "bnss",
    "indian_evidence_act_1872": "iea",
    "indian_evidence_act": "iea",
    "bharatiya_sakshya_adhiniyam_2023": "bsa",
    "bharatiya_sakshya_adhiniyam": "bsa",
    "constitution_of_india": "constitution",
    "constitution": "constitution",
}
