"""Graph-first retriever.

Runs a bounded, authority-weighted, typed BFS from a set of seed node ids.

Design:
  - The frontier is a priority queue keyed on ``(depth, -authority_score,
    -edge_priority)``. Higher-authority / structurally important nodes are
    expanded first so we exhaust the budget on useful neighbourhoods.
  - Edges are filtered by an intent-dependent allow-list (e.g. a statute_lookup
    query lets us walk SECTION_CROSSWALK_TO but not CASE_CITES_CASE).
  - Temporal validity: if ``as_of`` is provided, nodes with
    ``valid_to`` < ``as_of`` are excluded (soft — missing validity is accepted).
  - Matter-scope isolation: any node with a ``matter_id`` different from
    ``matter_scope`` is excluded.

A separate, best-effort Graphiti semantic pass is also run (if available) and
its nodes are folded in. When Graphiti is unreachable the retriever silently
falls back to the typed BFS result only.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from ..core import get_logger, settings
from ..graph import Neo4jAdapter, get_graphiti
from ..ontology import EdgeType
from .intent import QueryIntent


log = get_logger("retrieval.graph")


# ---------------------------------------------------------------------------
# Edge priority policy, indexed by query intent.
# ---------------------------------------------------------------------------
#
# Each value is an ordered tuple: most-preferred edge first. Edges not in the
# list can still be walked (they are de-prioritised), unless the intent has
# ``restrictive=True`` (e.g. a pure statute lookup).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _Policy:
    priority: tuple[str, ...]
    restrictive: bool = False


_DEFAULT_PRIORITY: tuple[str, ...] = (
    EdgeType.CHAPTER_CONTAINS_SECTION,
    EdgeType.SECTION_CONTAINS_SUBSECTION,
    EdgeType.SECTION_HAS_PROVISO,
    EdgeType.SECTION_HAS_EXPLANATION,
    EdgeType.SECTION_HAS_ILLUSTRATION,
    EdgeType.SECTION_CROSSWALK_TO,
    EdgeType.SECTION_AMENDED_BY,
    EdgeType.SECTION_PRESCRIBES_PUNISHMENT,
    EdgeType.OFFENCE_HAS_INGREDIENT,
    EdgeType.CASE_INTERPRETS_SECTION,
    EdgeType.CASE_CITES_CASE,
    EdgeType.CASE_APPLIES_STATUTE,
    EdgeType.PARAGRAPH_SUPPORTS_HOLDING,
    EdgeType.HOLDING_RESOLVES_ISSUE,
    EdgeType.DOCUMENT_CONTAINS_FACT,
    EdgeType.EXHIBIT_SUPPORTS_FACT,
    EdgeType.WITNESS_STATES_FACT,
    EdgeType.FACT_LINKED_TO_INGREDIENT,
    EdgeType.FACT_LINKED_TO_OFFENCE,
    EdgeType.FACT_RELEVANT_TO_ISSUE,
)


_INTENT_POLICIES: dict[QueryIntent, _Policy] = {
    QueryIntent.STATUTE_LOOKUP: _Policy(
        priority=(
            EdgeType.CHAPTER_CONTAINS_SECTION,
            EdgeType.SECTION_CONTAINS_SUBSECTION,
            EdgeType.SECTION_HAS_PROVISO,
            EdgeType.SECTION_HAS_EXPLANATION,
            EdgeType.SECTION_HAS_ILLUSTRATION,
            EdgeType.SECTION_CROSSWALK_TO,
            EdgeType.SECTION_AMENDED_BY,
        ),
        restrictive=False,
    ),
    QueryIntent.CROSSWALK: _Policy(
        priority=(
            EdgeType.SECTION_CROSSWALK_TO,
            EdgeType.SECTION_CONTAINS_SUBSECTION,
            EdgeType.CHAPTER_CONTAINS_SECTION,
        ),
        restrictive=True,
    ),
    QueryIntent.OFFENCE_INGREDIENT: _Policy(
        priority=(
            EdgeType.OFFENCE_HAS_INGREDIENT,
            EdgeType.SECTION_PRESCRIBES_PUNISHMENT,
            EdgeType.CASE_INTERPRETS_SECTION,
        ),
    ),
    QueryIntent.PUNISHMENT_LOOKUP: _Policy(
        priority=(
            EdgeType.SECTION_PRESCRIBES_PUNISHMENT,
            EdgeType.SECTION_CONTAINS_SUBSECTION,
            EdgeType.SECTION_HAS_PROVISO,
            EdgeType.CASE_INTERPRETS_SECTION,
        ),
    ),
    QueryIntent.PROCEDURE_LOOKUP: _Policy(
        priority=(
            EdgeType.PROCEDURE_GOVERNED_BY_SECTION,
            EdgeType.CASE_APPLIES_STATUTE,
            EdgeType.CHAPTER_CONTAINS_SECTION,
        ),
    ),
    QueryIntent.EVIDENCE_RULE_LOOKUP: _Policy(
        priority=(
            EdgeType.EVIDENCE_RULE_GOVERNED_BY_SECTION,
            EdgeType.SECTION_HAS_EXPLANATION,
            EdgeType.CASE_INTERPRETS_SECTION,
        ),
    ),
    QueryIntent.CASE_LAW_RETRIEVAL: _Policy(
        priority=(
            EdgeType.CASE_INTERPRETS_SECTION,
            EdgeType.PARAGRAPH_SUPPORTS_HOLDING,
            EdgeType.HOLDING_RESOLVES_ISSUE,
            EdgeType.CASE_CITES_CASE,
            EdgeType.CASE_FOLLOWS_CASE,
            EdgeType.CASE_OVERRULES_CASE,
            EdgeType.CASE_DISTINGUISHES_CASE,
        ),
    ),
    QueryIntent.PRECEDENT_TRACING: _Policy(
        priority=(
            EdgeType.CASE_CITES_CASE,
            EdgeType.CASE_FOLLOWS_CASE,
            EdgeType.CASE_DISTINGUISHES_CASE,
            EdgeType.CASE_OVERRULES_CASE,
            EdgeType.PARAGRAPH_SUPPORTS_HOLDING,
        ),
    ),
    QueryIntent.PRIVATE_EVIDENCE_CROSS: _Policy(
        priority=(
            EdgeType.DOCUMENT_CONTAINS_FACT,
            EdgeType.EXHIBIT_SUPPORTS_FACT,
            EdgeType.EXHIBIT_CONTRADICTS_FACT,
            EdgeType.WITNESS_STATES_FACT,
            EdgeType.FACT_LINKED_TO_INGREDIENT,
            EdgeType.FACT_LINKED_TO_OFFENCE,
            EdgeType.FACT_RELEVANT_TO_ISSUE,
            EdgeType.FACT_OCCURS_AT_TIME,
        ),
    ),
    QueryIntent.CONTRADICTION: _Policy(
        priority=(
            EdgeType.EXHIBIT_CONTRADICTS_FACT,
            EdgeType.ARGUMENT_CONTRADICTS_ARGUMENT,
            EdgeType.WITNESS_STATES_FACT,
            EdgeType.DOCUMENT_CONTAINS_FACT,
        ),
    ),
    QueryIntent.TIMELINE: _Policy(
        priority=(
            EdgeType.FACT_OCCURS_AT_TIME,
            EdgeType.DOCUMENT_CONTAINS_FACT,
            EdgeType.WITNESS_STATES_FACT,
        ),
    ),
}


class GraphStoreProto(Protocol):
    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    async def neighbors(
        self,
        node_id: str,
        *,
        edge_types: tuple[str, ...] | None = None,
        direction: str = "any",
    ) -> list[dict[str, Any]]: ...


@dataclass
class GraphRetrievalResult:
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)
    edges: list[dict[str, Any]] = field(default_factory=list)
    paths: list[list[str]] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)


class GraphRetriever:
    def __init__(self, store: GraphStoreProto | None = None) -> None:
        self.store: GraphStoreProto = store or Neo4jAdapter()
        self.graphiti = get_graphiti()

    async def retrieve(
        self,
        *,
        query: str,
        seeds: list[str],
        intent: QueryIntent = QueryIntent.GENERIC,
        matter_scope: str | None = None,
        authority_ceiling: int | None = None,
        as_of: str | None = None,
    ) -> GraphRetrievalResult:
        result = GraphRetrievalResult()
        if seeds:
            await self._typed_bfs(
                seeds=seeds,
                intent=intent,
                matter_scope=matter_scope,
                authority_ceiling=authority_ceiling,
                as_of=as_of,
                result=result,
            )

        # Graphiti fold-in. Best effort; failures are logged but swallowed.
        group_ids = [matter_scope] if matter_scope else None
        try:
            hits = await self.graphiti.search(
                query=query,
                group_ids=group_ids,
                num_results=settings.semantic_seed_topk,
            )
        except Exception as e:  # noqa: BLE001
            log.warning("graphiti.search_failed", error=str(e))
            hits = []
        for h in hits:
            # graphiti-core >= ~0.5 returns pydantic ``EntityEdge`` /
            # ``EntityNode`` objects from ``search()`` instead of plain dicts.
            # We dump to dict so the rest of the orchestrator stays agnostic
            # to graphiti's internal type churn.
            h_type = type(h).__name__
            if hasattr(h, "model_dump"):
                h = h.model_dump(mode="json")
            elif not isinstance(h, dict):
                # last-resort: pull public attributes off the object
                h = {k: getattr(h, k) for k in dir(h) if not k.startswith("_")}
            nid = h.get("node_uuid") or h.get("uuid") or h.get("id")
            if not nid or nid in result.nodes:
                continue
            # ``EntityEdge`` hits carry the grounded summary on ``fact`` and
            # point at the Episodic nodes that justified the relation via
            # ``episodes``. We stash both so the evidence builder can fall back
            # to the fact when no SourceSpan edge is attached to the uuid
            # (edges have no ``NODE_DERIVED_FROM_SOURCE`` themselves).
            fact = h.get("fact") or ""
            summary = h.get("summary") or fact
            excerpt = fact or summary
            result.nodes[nid] = {
                "id": nid,
                "source": "graphiti",
                "name": h.get("name"),
                "summary": summary,
                "excerpt": excerpt,
                "authority_tier": int(h.get("authority_tier", 8)),
                "node_type": h.get("node_type", "SummaryNode"),
                "graphiti_kind": h_type,
                "source_node_uuid": h.get("source_node_uuid"),
                "target_node_uuid": h.get("target_node_uuid"),
                "episodes": h.get("episodes") or [],
                "score": float(h.get("score", 0.0)),
            }

        result.debug = {
            "seed_count": len(seeds),
            "nodes": len(result.nodes),
            "intent": intent.value,
        }
        log.info(
            "graph.retrieve",
            seeds=len(seeds),
            nodes=len(result.nodes),
            paths=len(result.paths),
            intent=intent.value,
        )
        return result

    # --- typed BFS -----------------------------------------------------

    async def _typed_bfs(
        self,
        *,
        seeds: list[str],
        intent: QueryIntent,
        matter_scope: str | None,
        authority_ceiling: int | None,
        as_of: str | None,
        result: GraphRetrievalResult,
    ) -> None:
        policy = _INTENT_POLICIES.get(intent)
        priority_list = policy.priority if policy else _DEFAULT_PRIORITY
        priority_index = {et: i for i, et in enumerate(priority_list)}
        restrict = bool(policy and policy.restrictive)
        allowed_types = set(priority_list) if restrict else None

        max_hops = settings.graph_max_hops
        max_nodes = settings.graph_max_nodes
        fanout = settings.graph_frontier_fanout

        # priority queue entries: (depth, -authority_bonus, -edge_bonus, counter, node_id, parent_id, edge_type)
        counter = 0
        frontier: list[tuple[int, float, float, int, str, str | None, str | None]] = []
        parents: dict[str, tuple[str, str]] = {}  # node_id -> (parent_id, edge_type)

        for sid in seeds:
            node = await self.store.get_node(sid)
            if node is None:
                continue
            if not _admissible(node, matter_scope=matter_scope,
                               authority_ceiling=authority_ceiling, as_of=as_of):
                continue
            result.nodes[sid] = dict(node)
            result.nodes[sid].setdefault("score", 0.0)
            heapq.heappush(
                frontier,
                (0, -_authority_bonus(node), 0.0, counter, sid, None, None),
            )
            counter += 1

        while frontier and len(result.nodes) < max_nodes:
            depth, _, _, _, nid, parent, in_edge = heapq.heappop(frontier)
            if depth >= max_hops:
                continue

            edge_types = tuple(priority_list) if restrict else None
            try:
                neigh = await self.store.neighbors(nid, edge_types=edge_types)
            except Exception as e:  # noqa: BLE001
                log.warning("graph.neighbors_failed", node=nid, error=str(e))
                continue

            # Order neighbours by the intent-driven priority so the best edges
            # are admitted first when we hit the budget.
            neigh.sort(key=lambda r: priority_index.get(r.get("edge_type", ""), 999))
            neigh = neigh[:fanout]

            for rec in neigh:
                etype = rec.get("edge_type", "")
                other = rec.get("node", {})
                other_id = other.get("id")
                if not other_id:
                    continue

                # record edge (always, even if we've already visited the other node)
                result.edges.append(
                    {
                        "type": etype,
                        "src": nid if rec.get("edge_direction") == "out" else other_id,
                        "dst": other_id if rec.get("edge_direction") == "out" else nid,
                        "props": dict(rec.get("edge_props") or {}),
                    }
                )

                if other_id in result.nodes:
                    continue
                if not _admissible(
                    other,
                    matter_scope=matter_scope,
                    authority_ceiling=authority_ceiling,
                    as_of=as_of,
                ):
                    continue
                if len(result.nodes) >= max_nodes:
                    break

                result.nodes[other_id] = dict(other)
                result.nodes[other_id].setdefault("score", _edge_bonus(etype, priority_index))
                parents[other_id] = (nid, etype)

                edge_bonus = _edge_bonus(etype, priority_index)
                auth_bonus = _authority_bonus(other)
                heapq.heappush(
                    frontier,
                    (depth + 1, -auth_bonus, -edge_bonus, counter, other_id, nid, etype),
                )
                counter += 1

        # Build paths: walk parent pointers back to the seed for every node.
        for nid in result.nodes.keys():
            path = _reconstruct_path(nid, parents)
            if len(path) > 1:
                result.paths.append(path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _admissible(
    node: dict[str, Any],
    *,
    matter_scope: str | None,
    authority_ceiling: int | None,
    as_of: str | None,
) -> bool:
    # authority ceiling
    if authority_ceiling is not None:
        tier = node.get("authority_tier")
        if tier is not None and int(tier) > authority_ceiling:
            return False
    # matter isolation
    mscope = node.get("matter_id")
    if mscope and matter_scope and mscope != matter_scope:
        return False
    if mscope and not matter_scope:
        return False  # never leak private content to public queries
    # temporal validity (soft)
    if as_of:
        vt = node.get("valid_to") or node.get("validity_end")
        if vt and _before(vt, as_of):
            return False
    return True


def _authority_bonus(node: dict[str, Any]) -> float:
    tier = node.get("authority_tier")
    try:
        t = int(tier) if tier is not None else 5
    except (TypeError, ValueError):
        t = 5
    return 1.0 / max(t, 1)


def _edge_bonus(etype: str, priority_index: dict[str, int]) -> float:
    rank = priority_index.get(etype)
    if rank is None:
        return 0.1
    return 1.0 - (rank / max(len(priority_index), 1)) * 0.8


def _before(a: str, b: str) -> bool:
    try:
        return datetime.fromisoformat(str(a)) < datetime.fromisoformat(str(b))
    except ValueError:
        return False


def _reconstruct_path(nid: str, parents: dict[str, tuple[str, str]]) -> list[str]:
    path: list[str] = []
    cur: str | None = nid
    guard = 0
    while cur is not None and guard < 64:
        path.append(cur)
        if cur not in parents:
            break
        parent, etype = parents[cur]
        path.append(etype)
        cur = parent
        guard += 1
    path.reverse()
    return path
