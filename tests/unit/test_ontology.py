from __future__ import annotations

import pytest

from services.lib.ontology import (
    EdgeType,
    NodeType,
    OntologyViolation,
    authority_tier_for,
    validate_edge,
    validate_node,
)
from services.lib.ontology.authority import AuthorityTier


def test_node_type_enum_is_closed():
    assert NodeType.SECTION in NodeType
    assert NodeType("Section") is NodeType.SECTION


def test_validate_node_requires_properties():
    with pytest.raises(OntologyViolation):
        validate_node(NodeType.SECTION, {"number": "378"})  # missing act_ref
    validate_node(NodeType.SECTION, {"number": "378", "act_ref": "IPC"})


def test_validate_edge_endpoints():
    validate_edge(
        EdgeType.CHAPTER_CONTAINS_SECTION,
        NodeType.CHAPTER,
        NodeType.SECTION,
    )
    with pytest.raises(OntologyViolation):
        validate_edge(
            EdgeType.CHAPTER_CONTAINS_SECTION,
            NodeType.SECTION,
            NodeType.CHAPTER,
        )


def test_temporal_edge_requires_as_of():
    with pytest.raises(OntologyViolation):
        validate_edge(
            EdgeType.SECTION_CROSSWALK_TO,
            NodeType.SECTION,
            NodeType.SECTION,
            {},
        )
    validate_edge(
        EdgeType.SECTION_CROSSWALK_TO,
        NodeType.SECTION,
        NodeType.SECTION,
        {"as_of": "2023-12"},
    )


def test_authority_tier_statute():
    assert authority_tier_for(NodeType.SECTION) == AuthorityTier.CONSTITUTION_STATUTE


def test_authority_tier_judicial_contextual():
    assert authority_tier_for(NodeType.CASE, court_level="SC") == AuthorityTier.SUPREME_COURT
    assert authority_tier_for(NodeType.CASE, court_level="HC") == AuthorityTier.HIGH_COURT
    assert authority_tier_for(NodeType.CASE) == AuthorityTier.HIGH_COURT  # conservative default
