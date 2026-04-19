"""In-memory stand-in for Neo4jAdapter — used by tests and dry-run mode.

Implements the same surface the GraphWriter calls: ``ensure_constraints``,
``upsert_node``, ``upsert_edge``, ``neighborhood``. Provides a ``snapshot()``
so tests can assert on the graph state.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ..ontology import EdgeType, NodeType, validate_edge, validate_node


class InMemoryGraphStore:
    def __init__(self) -> None:
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, Any]] = []
        self._adj: dict[str, list[int]] = defaultdict(list)

    async def ensure_constraints(self) -> None:
        return None

    async def close(self) -> None:
        return None

    async def upsert_node(
        self,
        *,
        node_type: NodeType,
        node_id: str,
        props: dict[str, Any],
    ) -> None:
        validate_node(node_type, props)
        existing = self.nodes.get(node_id, {})
        existing.update({**props, "id": node_id, "node_type": node_type.value})
        self.nodes[node_id] = existing

    async def upsert_edge(
        self,
        *,
        edge_type: EdgeType,
        src_type: NodeType,
        src_id: str,
        dst_type: NodeType,
        dst_id: str,
        props: dict[str, Any] | None = None,
    ) -> None:
        props = props or {}
        validate_edge(edge_type, src_type, dst_type, props)
        if src_id not in self.nodes:
            # allow provenance edges even when node not yet upserted
            self.nodes[src_id] = {"id": src_id, "node_type": src_type.value}
        if dst_id not in self.nodes:
            self.nodes[dst_id] = {"id": dst_id, "node_type": dst_type.value}
        edge = {
            "type": edge_type.value,
            "src": src_id,
            "dst": dst_id,
            "src_type": src_type.value,
            "dst_type": dst_type.value,
            "props": props,
        }
        idx = len(self.edges)
        self.edges.append(edge)
        self._adj[src_id].append(idx)
        self._adj[dst_id].append(idx)

    async def neighborhood(
        self,
        *,
        seeds: list[str],
        max_hops: int,
        max_nodes: int,
        authority_ceiling: int | None = None,
        matter_scope: str | None = None,
    ) -> dict[str, Any]:
        visited: dict[str, dict[str, Any]] = {}
        frontier = [(s, 0) for s in seeds if s in self.nodes]
        edges_out: list[dict[str, Any]] = []
        while frontier and len(visited) < max_nodes:
            nid, depth = frontier.pop(0)
            if nid in visited:
                continue
            node = self.nodes[nid]
            if authority_ceiling is not None and node.get("authority_tier", 0):
                if node["authority_tier"] > authority_ceiling:
                    continue
            if matter_scope is not None:
                mscope = node.get("matter_id")
                if mscope and mscope != matter_scope:
                    continue
            visited[nid] = node
            if depth >= max_hops:
                continue
            for ei in self._adj.get(nid, []):
                e = self.edges[ei]
                other = e["dst"] if e["src"] == nid else e["src"]
                if other not in visited:
                    frontier.append((other, depth + 1))
                edges_out.append(e)
        return {"nodes": visited, "edges": edges_out}

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        n = self.nodes.get(node_id)
        return dict(n) if n else None

    async def find_nodes(
        self,
        *,
        node_type: str | None = None,
        props: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        props = props or {}
        out: list[dict[str, Any]] = []
        for n in self.nodes.values():
            if node_type is not None and n.get("node_type") != node_type:
                continue
            if any(str(n.get(k, "")).lower() != str(v).lower() for k, v in props.items()):
                continue
            out.append(dict(n))
            if len(out) >= limit:
                break
        return out

    async def lookup_case_by_citation(self, citation: str) -> str | None:
        needle = citation.lower()
        for n in self.nodes.values():
            if n.get("node_type") != "Case":
                continue
            citations = n.get("citations") or []
            if isinstance(citations, str):
                citations = [citations]
            if any(str(c).lower() == needle for c in citations):
                return n.get("id")
        return None

    async def get_span_for_node(self, node_id: str) -> dict[str, Any] | None:
        for ei in self._adj.get(node_id, []):
            e = self.edges[ei]
            if e["type"] != "NODE_DERIVED_FROM_SOURCE" or e["src"] != node_id:
                continue
            other = self.nodes.get(e["dst"])
            if other and other.get("node_type") == "SourceSpan":
                return dict(other)
        return None

    async def neighbors(
        self,
        node_id: str,
        *,
        edge_types: tuple[str, ...] | None = None,
        direction: str = "any",
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for ei in self._adj.get(node_id, []):
            e = self.edges[ei]
            if edge_types and e["type"] not in edge_types:
                continue
            if direction == "out" and e["src"] != node_id:
                continue
            if direction == "in" and e["dst"] != node_id:
                continue
            other_id = e["dst"] if e["src"] == node_id else e["src"]
            node = dict(self.nodes.get(other_id, {"id": other_id}))
            out.append(
                {
                    "edge_type": e["type"],
                    "edge_direction": "out" if e["src"] == node_id else "in",
                    "edge_props": dict(e.get("props") or {}),
                    "node": node,
                }
            )
        return out

    # -- test helpers ------------------------------------------------------

    def count_nodes(self, node_type: str | None = None) -> int:
        if node_type is None:
            return len(self.nodes)
        return sum(1 for n in self.nodes.values() if n.get("node_type") == node_type)

    def count_edges(self, edge_type: str | None = None) -> int:
        if edge_type is None:
            return len(self.edges)
        return sum(1 for e in self.edges if e["type"] == edge_type)
