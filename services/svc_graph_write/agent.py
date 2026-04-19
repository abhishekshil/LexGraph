"""GraphWriterAgent: the only agent allowed to mutate the graph.

Receives EnrichCompletedEvent, validates every node/edge against the ontology,
writes via GraphWriter (which also adds NODE_DERIVED_FROM_SOURCE and authority
tiers), and publishes graph.written.
"""

from __future__ import annotations

from services.lib.audit import provenance_audit
from services.lib.bus.factory import Streams
from services.lib.data_models.events import (
    EnrichCompletedEvent,
    Event,
    GraphWrittenEvent,
)
from services.lib.graph import GraphWriter
from services.lib.indexing import INDEXABLE_NODE_TYPES
from services.lib.ontology import EdgeType, NodeType, OntologyViolation, authority_tier_for
from services.agent_base import Agent


class GraphWriterAgent(Agent):
    name = "graph_writer"
    listens = (Streams.ENRICH_COMPLETED,)
    publishes = (Streams.GRAPH_WRITTEN,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.writer = GraphWriter()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, EnrichCompletedEvent):
            return

        await self.writer.bootstrap()

        written_nodes: list[str] = []
        indexable: list[dict[str, object]] = []
        for n in event.nodes:
            try:
                nt = NodeType(n["node_type"])
            except ValueError:
                self.log.warning("unknown_node_type", node_type=n.get("node_type"))
                continue
            court_level = n["props"].get("level")
            try:
                await self.writer.upsert(
                    node_type=nt,
                    node_id=n["node_id"],
                    props=n["props"],
                    provenance_span_id=n["provenance_span_id"],
                    register_as_graphiti_episode=bool(n.get("register_as_graphiti_episode", False)),
                    court_level=court_level,
                )
                written_nodes.append(n["node_id"])
                if nt in INDEXABLE_NODE_TYPES:
                    indexable.append(
                        _indexable_payload(
                            node_type=nt,
                            node_id=n["node_id"],
                            props=n["props"],
                            provenance_span_id=n["provenance_span_id"],
                            court_level=court_level,
                        )
                    )
            except OntologyViolation as e:
                self.log.warning(
                    "ontology_violation_node",
                    node=n.get("node_id"),
                    node_type=n.get("node_type"),
                    error=str(e),
                )

        edge_count = 0
        for e in event.edges:
            try:
                await self.writer.link(
                    edge_type=EdgeType(e["edge_type"]),
                    src_type=NodeType(e["src_type"]),
                    src_id=e["src_id"],
                    dst_type=NodeType(e["dst_type"]),
                    dst_id=e["dst_id"],
                    props=e.get("props") or {},
                )
                edge_count += 1
            except OntologyViolation as err:
                self.log.warning("ontology_violation_edge", edge=e, error=str(err))
            except Exception as err:
                self.log.warning("edge_write_failed", edge=e, error=str(err))

        out = GraphWrittenEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            episode_id=event.episode_id,
            node_ids=written_nodes,
            edge_count=edge_count,
            indexable=indexable,
        )
        await self.bus.publish(Streams.GRAPH_WRITTEN, out)
        await provenance_audit.log(
            "graph.written",
            trace_id=event.trace_id,
            episode_id=event.episode_id,
            nodes=len(written_nodes),
            edges=edge_count,
            matter_id=event.matter_id,
        )
        self.log.info(
            "graph.written",
            episode_id=event.episode_id,
            nodes=len(written_nodes),
            edges=edge_count,
            indexable=len(indexable),
        )


def _indexable_payload(
    *,
    node_type: NodeType,
    node_id: str,
    props: dict[str, object],
    provenance_span_id: str,
    court_level: str | None,
) -> dict[str, object]:
    """Package everything the IndexAgent needs to build a Qdrant point."""
    text = str(props.get("text") or props.get("label") or props.get("heading") or "")
    title = props.get("heading") or props.get("title") or props.get("short_title")
    number = props.get("number")
    act_ref = props.get("act_ref") or props.get("section_ref")
    section_ref = None
    if node_type == NodeType.SECTION and number and act_ref:
        section_ref = f"section:{str(act_ref).lower()}:{str(number).lower()}"
    case_ref = props.get("case_ref") if node_type in {NodeType.PARAGRAPH, NodeType.HOLDING, NodeType.RATIO, NodeType.OBITER} else None
    return {
        "node_id": node_id,
        "node_type": node_type.value,
        "text": text[:4000],
        "authority_tier": int(authority_tier_for(node_type, court_level=court_level)),
        "matter_id": props.get("matter_id") or props.get("matter_ref") or None,
        "source_span_id": provenance_span_id,
        "section_ref": section_ref,
        "case_ref": case_ref,
        "title": title,
        "citation": props.get("citation"),
        "court": props.get("court"),
        "date": props.get("decision_date") or props.get("date"),
    }
