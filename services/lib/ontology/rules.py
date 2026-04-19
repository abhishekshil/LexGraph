"""Structural + provenance invariants enforced before any write reaches the graph.

If validate_node / validate_edge raise OntologyViolation, the graph writer
drops the event onto a dead-letter stream so it can be inspected rather than
silently corrupting the graph.
"""

from __future__ import annotations

from typing import Any

from .edge_types import EDGE_SCHEMAS, EdgeType
from .node_types import NodeType


class OntologyViolation(ValueError):
    """Raised when a node/edge breaks an ontology invariant."""


# Required properties per node type. Keep the set deliberately small; extras
# are allowed but these must exist before a node is accepted.
REQUIRED_PROPS: dict[NodeType, tuple[str, ...]] = {
    NodeType.ACT: ("short_title", "jurisdiction"),
    NodeType.AMENDMENT: ("amending_act", "date_enforced"),
    NodeType.SECTION: ("number", "act_ref"),
    NodeType.SUBSECTION: ("number", "section_ref"),
    NodeType.PROVISO: ("parent_ref",),
    NodeType.EXPLANATION: ("parent_ref",),
    NodeType.ILLUSTRATION: ("parent_ref",),
    NodeType.CASE: ("title", "court_ref", "decision_date"),
    NodeType.COURT: ("name", "level"),
    NodeType.JUDGE: ("name",),
    NodeType.CITATION: ("text",),
    NodeType.PARAGRAPH: ("number", "case_ref"),
    NodeType.OFFENCE: ("name", "governing_section_ref"),
    NodeType.INGREDIENT: ("description", "offence_ref"),
    NodeType.PUNISHMENT: ("kind", "section_ref"),
    NodeType.MATTER: ("matter_id", "title"),
    NodeType.DOCUMENT: ("matter_ref", "filename", "kind"),
    NodeType.WITNESS: ("name", "matter_ref"),
    NodeType.EXHIBIT: ("label", "document_ref"),
    NodeType.FACT: ("description", "matter_ref"),
    NodeType.SOURCE_EPISODE: ("kind", "origin", "ingested_at", "hash"),
    NodeType.SOURCE_SPAN: ("episode_ref", "file_ref", "char_start", "char_end"),
    NodeType.FILE: ("storage_uri", "sha256"),
    NodeType.VALIDITY_PERIOD: ("start",),
}


def validate_node(node_type: NodeType, props: dict[str, Any]) -> None:
    if node_type not in NodeType:
        raise OntologyViolation(f"unknown node type: {node_type}")

    required = REQUIRED_PROPS.get(node_type, ())
    missing = [p for p in required if p not in props or props[p] in (None, "", [])]
    if missing:
        raise OntologyViolation(
            f"{node_type} is missing required properties: {missing}"
        )

    # Provenance floor: every non-system node must be linked via
    # NODE_DERIVED_FROM_SOURCE at write-time. This is enforced at the graph
    # writer level (see services/graph/writer.py) - here we only surface the
    # expectation via a property marker that the writer sets after the linking
    # edge is created. If the writer fails to link, it rolls back the node.


def validate_edge(
    edge_type: EdgeType,
    src_type: NodeType,
    dst_type: NodeType,
    props: dict[str, Any] | None = None,
) -> None:
    schema = EDGE_SCHEMAS.get(edge_type)
    if schema is None:
        raise OntologyViolation(f"unknown edge type: {edge_type}")
    if not schema.permits(src_type, dst_type):
        raise OntologyViolation(
            f"edge {edge_type} forbidden from {src_type} -> {dst_type}; "
            f"allowed: {schema.src} -> {schema.dst}"
        )
    props = props or {}
    if schema.temporal and "as_of" not in props and "validity_period_ref" not in props:
        raise OntologyViolation(
            f"edge {edge_type} is temporal and requires `as_of` or `validity_period_ref`"
        )
