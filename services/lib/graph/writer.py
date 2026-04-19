"""GraphWriter enforces provenance & authority invariants while writing.

Every write:
  1. validates node / edge against the ontology
  2. computes the authority tier
  3. creates the NODE_DERIVED_FROM_SOURCE edge to a SourceSpan or Episode
  4. optionally registers the node with Graphiti as a temporal episode
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ..core import get_logger
from ..data_models.provenance import SourceEpisode, SourceSpan
from ..ontology import EdgeType, NodeType, authority_tier_for, validate_edge, validate_node
from .graphiti_client import get_graphiti
from .neo4j_adapter import Neo4jAdapter


log = get_logger("graph.writer")


class GraphWriter:
    """Single place every node/edge goes through. Keeps the graph clean."""

    def __init__(self, neo: Neo4jAdapter | None = None) -> None:
        self.neo = neo or Neo4jAdapter()
        self.graphiti = get_graphiti()

    async def bootstrap(self) -> None:
        await self.neo.ensure_constraints()

    # -- provenance root --

    async def register_file(self, file: dict[str, Any]) -> None:
        await self.neo.upsert_node(node_type=NodeType.FILE, node_id=file["id"], props=file)

    async def register_episode(self, episode: SourceEpisode) -> None:
        await self.neo.upsert_node(
            node_type=NodeType.SOURCE_EPISODE,
            node_id=episode.id,
            props={
                "kind": episode.kind,
                "origin": episode.origin,
                "ingested_at": episode.ingested_at.isoformat(),
                "hash": episode.hash,
                "matter_id": episode.matter_id,
                "attribution": episode.attribution,
            },
        )
        # episode -> file edge (using NODE_DERIVED_FROM_SOURCE both ways is wrong;
        # episodes reference files via `file_id` property. We keep structural
        # linkage here without inventing new edge types.)
        # If we want a labeled edge, we could add EPISODE_OF_FILE later.

    async def register_span(self, span: SourceSpan) -> None:
        await self.neo.upsert_node(
            node_type=NodeType.SOURCE_SPAN,
            node_id=span.id,
            props={
                "episode_ref": span.episode_id,
                "file_ref": span.file_id,
                "char_start": span.char_start,
                "char_end": span.char_end,
                "page": span.page,
                "text": span.text,
                "ocr_confidence": span.ocr_confidence,
                "matter_id": span.matter_id,
            },
        )
        # provenance self-edge to episode
        await self.neo.upsert_edge(
            edge_type=EdgeType.NODE_DERIVED_FROM_SOURCE,
            src_type=NodeType.SOURCE_SPAN,
            src_id=span.id,
            dst_type=NodeType.SOURCE_EPISODE,
            dst_id=span.episode_id,
        )

    # -- typed nodes --

    async def upsert(
        self,
        *,
        node_type: NodeType,
        node_id: str,
        props: dict[str, Any],
        provenance_span_id: str,
        court_level: str | None = None,
        register_as_graphiti_episode: bool = False,
    ) -> None:
        validate_node(node_type, props)
        tier = authority_tier_for(node_type, court_level=court_level)
        props = {**props, "authority_tier": int(tier), "court_level": court_level}

        await self.neo.upsert_node(node_type=node_type, node_id=node_id, props=props)
        await self.neo.upsert_edge(
            edge_type=EdgeType.NODE_DERIVED_FROM_SOURCE,
            src_type=node_type,
            src_id=node_id,
            dst_type=NodeType.SOURCE_SPAN,
            dst_id=provenance_span_id,
        )

        if register_as_graphiti_episode:
            # Mirror the most important semantic content into Graphiti so its
            # temporal / semantic search can surface it.
            episode_body = _episode_body(node_type, props)
            await self.graphiti.add_episode(
                name=f"{node_type.value}:{node_id}",
                episode_body=episode_body,
                source_description=f"provenance_span:{provenance_span_id}",
                reference_time=datetime.utcnow(),
                group_id=props.get("matter_id"),
                metadata={"node_type": node_type.value, "node_id": node_id},
            )
        log.debug("graph.upsert", node_type=str(node_type), node_id=node_id, tier=int(tier))

    async def link(
        self,
        *,
        edge_type: EdgeType,
        src_type: NodeType,
        src_id: str,
        dst_type: NodeType,
        dst_id: str,
        props: dict[str, Any] | None = None,
    ) -> None:
        validate_edge(edge_type, src_type, dst_type, props or {})
        await self.neo.upsert_edge(
            edge_type=edge_type,
            src_type=src_type,
            src_id=src_id,
            dst_type=dst_type,
            dst_id=dst_id,
            props=props or {},
        )


def _episode_body(node_type: NodeType, props: dict[str, Any]) -> str:
    """Produce a short textual body for Graphiti semantic indexing."""
    parts: list[str] = [f"[{node_type.value}]"]
    for k in ("title", "short_title", "name", "heading", "description", "citation"):
        v = props.get(k)
        if v:
            parts.append(str(v))
    if "text" in props:
        parts.append(str(props["text"])[:800])
    return " — ".join(parts)
