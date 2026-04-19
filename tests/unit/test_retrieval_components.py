"""Unit tests for Phase 3 retrieval components."""

from __future__ import annotations

import pytest

from services.lib.data_models.evidence import EvidencePack, EvidenceSpan
from services.lib.graph import InMemoryGraphStore
from services.lib.indexing.embedder import Embedder, _hash_embed
from services.lib.indexing.payload import INDEXABLE_NODE_TYPES, IndexPayload, payload_to_dict
from services.lib.ontology import NodeType
from services.lib.ontology.authority import AuthorityTier
from services.lib.reranking.authority_reranker import AuthorityReranker
from services.lib.reranking.semantic_reranker import SemanticReranker
from services.lib.retrieval.evidence_builder import (
    _approx_tokens,
    _confidence_from,
    _detect_conflicts,
    _evict_lowest_tier,
    _intent_from,
)
from services.lib.retrieval.graph_retriever import GraphRetriever
from services.lib.retrieval.intent import QueryIntent, classify_intent
from services.lib.retrieval.seeds import _act_token, _section_node_id, find_seed_nodes


# ---------------------------------------------------------------------------
# seeds
# ---------------------------------------------------------------------------

def test_act_token_resolves_ipc_variants():
    assert _act_token("IPC") == "ipc"
    assert _act_token("Indian Penal Code") == "ipc"
    assert _act_token("Indian Penal Code, 1860") == "ipc"
    assert _act_token("Bharatiya Nyaya Sanhita, 2023") == "bns"
    assert _act_token("Constitution of India") == "constitution"


def test_section_node_id_shape():
    assert _section_node_id("IPC", "378") == "section:ipc:378"
    assert _section_node_id("Indian Penal Code, 1860", "302") == "section:ipc:302"
    assert _section_node_id("IPC", None) is None


@pytest.mark.asyncio
async def test_find_seed_nodes_section_ref():
    store = InMemoryGraphStore()
    await store.upsert_node(
        node_type=NodeType.SECTION,
        node_id="section:ipc:378",
        props={"number": "378", "act_ref": "Indian Penal Code, 1860"},
    )
    seeds = await find_seed_nodes(
        "What does S.378 IPC say about theft?", store=store
    )
    assert "section:ipc:378" in seeds.node_ids


@pytest.mark.asyncio
async def test_find_seed_nodes_act_mention():
    store = InMemoryGraphStore()
    await store.upsert_node(
        node_type=NodeType.ACT,
        node_id="act:bns",
        props={"short_title": "Bharatiya Nyaya Sanhita", "jurisdiction": "IN"},
    )
    seeds = await find_seed_nodes("Under BNS, what is theft?", store=store)
    assert "act:bns" in seeds.node_ids


# ---------------------------------------------------------------------------
# intent classifier
# ---------------------------------------------------------------------------

def test_intent_classifier_recognises_punishment():
    res = classify_intent("What is the punishment for theft under S.378 IPC?")
    assert res.intent == QueryIntent.PUNISHMENT_LOOKUP


def test_intent_classifier_recognises_crosswalk():
    res = classify_intent("Map IPC 302 to BNS")
    assert res.intent == QueryIntent.CROSSWALK


# ---------------------------------------------------------------------------
# graph retriever (typed BFS)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_typed_bfs_walks_structural_edges():
    from services.lib.ontology import EdgeType

    store = InMemoryGraphStore()
    await store.upsert_node(
        node_type=NodeType.ACT,
        node_id="act:ipc",
        props={"short_title": "IPC", "jurisdiction": "IN", "authority_tier": 1},
    )
    await store.upsert_node(
        node_type=NodeType.SECTION,
        node_id="section:ipc:378",
        props={"number": "378", "act_ref": "IPC", "authority_tier": 1},
    )
    await store.upsert_node(
        node_type=NodeType.SECTION,
        node_id="section:ipc:379",
        props={"number": "379", "act_ref": "IPC", "authority_tier": 1},
    )
    await store.upsert_node(
        node_type=NodeType.CHAPTER,
        node_id="chapter:ipc:17",
        props={"number": "XVII", "authority_tier": 1},
    )
    await store.upsert_edge(
        edge_type=EdgeType.ACT_CONTAINS_CHAPTER,
        src_type=NodeType.ACT, src_id="act:ipc",
        dst_type=NodeType.CHAPTER, dst_id="chapter:ipc:17",
    )
    await store.upsert_edge(
        edge_type=EdgeType.CHAPTER_CONTAINS_SECTION,
        src_type=NodeType.CHAPTER, src_id="chapter:ipc:17",
        dst_type=NodeType.SECTION, dst_id="section:ipc:378",
    )
    await store.upsert_edge(
        edge_type=EdgeType.CHAPTER_CONTAINS_SECTION,
        src_type=NodeType.CHAPTER, src_id="chapter:ipc:17",
        dst_type=NodeType.SECTION, dst_id="section:ipc:379",
    )

    retriever = GraphRetriever(store=store)
    result = await retriever.retrieve(
        query="theft",
        seeds=["section:ipc:378"],
        intent=QueryIntent.STATUTE_LOOKUP,
    )
    assert "section:ipc:378" in result.nodes
    assert "chapter:ipc:17" in result.nodes
    # sibling should also be reachable within max_hops=3 via chapter
    assert "section:ipc:379" in result.nodes


@pytest.mark.asyncio
async def test_typed_bfs_respects_authority_ceiling():
    store = InMemoryGraphStore()
    await store.upsert_node(
        node_type=NodeType.SECTION,
        node_id="section:ipc:378",
        props={"number": "378", "act_ref": "IPC", "authority_tier": 1},
    )
    await store.upsert_node(
        node_type=NodeType.SUMMARY_NODE,
        node_id="summary:378",
        props={"label": "summary of theft", "authority_tier": 8},
    )
    from services.lib.ontology import EdgeType
    await store.upsert_edge(
        edge_type=EdgeType.NODE_SUMMARIZES_NEIGHBORHOOD,
        src_type=NodeType.SUMMARY_NODE, src_id="summary:378",
        dst_type=NodeType.SECTION, dst_id="section:ipc:378",
    )

    retriever = GraphRetriever(store=store)
    result = await retriever.retrieve(
        query="theft",
        seeds=["section:ipc:378"],
        intent=QueryIntent.STATUTE_LOOKUP,
        authority_ceiling=3,
    )
    assert "summary:378" not in result.nodes


# ---------------------------------------------------------------------------
# reranker
# ---------------------------------------------------------------------------

def test_authority_reranker_prefers_higher_tiers():
    r = AuthorityReranker()
    cands = [
        {"id": "a", "authority_tier": 8},
        {"id": "b", "authority_tier": 1},
        {"id": "c", "authority_tier": 3},
    ]
    ranked = r.rank(cands)
    assert ranked[0]["id"] == "b"
    assert ranked[-1]["id"] == "a"


def test_semantic_reranker_falls_back_to_lexical():
    r = SemanticReranker()
    # Force the lexical fallback by pretending the model isn't available.
    r._model = False
    cands = [
        {"id": "a", "text": "about theft and property"},
        {"id": "b", "text": "about contract law"},
        {"id": "c", "text": "theft theft theft of movable property"},
    ]
    ranked = r.rank("theft movable property", cands)
    assert ranked[0]["id"] == "c"


# ---------------------------------------------------------------------------
# evidence builder
# ---------------------------------------------------------------------------

def test_approx_tokens_monotonic():
    assert _approx_tokens("") == 0
    a = _approx_tokens("a few short words")
    b = _approx_tokens("a few short words " * 10)
    assert b > a


def test_intent_from_accepts_known_and_unknown():
    assert _intent_from("statute_lookup") == QueryIntent.STATUTE_LOOKUP
    assert _intent_from("nope") == QueryIntent.GENERIC


def _mk_span(marker, tier, section="Section 378 IPC"):
    return EvidenceSpan(
        marker=marker,
        node_id=f"n-{marker}",
        node_type="Section",
        source_span_id=f"sp-{marker}",
        source_episode_id="ep-x",
        file_id="f-x",
        section_or_paragraph=section,
        excerpt="x" * 200,
        char_start=0,
        char_end=200,
        tier=AuthorityTier(tier),
        kind="public",
    )


def test_evict_lowest_tier_removes_weakest():
    spans = [_mk_span("S1", 1), _mk_span("S2", 5), _mk_span("S3", 3)]
    _evict_lowest_tier(spans)
    assert "S2" not in [s.marker for s in spans]


def test_detect_conflicts_surfaces_tier_disagreement():
    spans = [
        _mk_span("S1", 1, section="Section 378 IPC"),
        _mk_span("S2", 3, section="Section 378 IPC"),
    ]
    conflicts = _detect_conflicts(spans)
    assert conflicts
    assert "section 378 ipc" in conflicts[0]["topic"].lower()


def test_confidence_from_tier_mix():
    spans = [_mk_span("S1", 1), _mk_span("S2", 2)]
    assert _confidence_from(spans, intent=QueryIntent.STATUTE_LOOKUP) == "high"
    spans_med = [_mk_span("S1", 3)]
    assert _confidence_from(spans_med, intent=QueryIntent.GENERIC) == "medium"


# ---------------------------------------------------------------------------
# indexing
# ---------------------------------------------------------------------------

def test_hash_embed_deterministic_and_normalised():
    v1 = _hash_embed("theft of movable property")
    v2 = _hash_embed("theft of movable property")
    assert v1 == v2
    import math
    norm = math.sqrt(sum(x * x for x in v1))
    assert 0.99 < norm < 1.01


def test_payload_flattens_extras():
    p = IndexPayload(
        node_id="n",
        node_type="Section",
        text="hello",
        authority_tier=1,
        extras={"foo": "bar", "none_val": None},
    )
    d = payload_to_dict(p)
    assert d["node_id"] == "n"
    assert d["ex.foo"] == "bar"
    assert "ex.none_val" not in d
    assert "extras" not in d


def test_indexable_node_types_covers_core():
    assert NodeType.SECTION in INDEXABLE_NODE_TYPES
    assert NodeType.PARAGRAPH in INDEXABLE_NODE_TYPES
    # Structural containers are NOT indexed directly.
    assert NodeType.ACT not in INDEXABLE_NODE_TYPES


def test_embedder_hash_fallback_round_trip():
    e = Embedder()
    # Force the fallback path (no sentence-transformers required on CI).
    e._degraded = True
    vec = e.encode_one("theft of property")
    assert isinstance(vec, list) and len(vec) == 256
    assert e.model_name == "hash-fallback"
