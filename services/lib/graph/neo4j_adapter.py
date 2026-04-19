"""Direct Neo4j adapter for typed ontology writes and traversals.

Graphiti handles temporal episodes + semantic relations autonomously. We also
maintain a *typed ontology layer* in Neo4j (labels = NodeType, rel types =
EdgeType) for deterministic structural queries (section hierarchy, crosswalks,
citation networks). Queries hit both:
  - Graphiti for semantic + temporal search
  - Neo4j directly for structural / authority-ranked traversal

Both live in the same Neo4j database; we just use different labels/rel types.
"""

from __future__ import annotations

from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase

from ..core import get_logger, settings
from ..ontology import EdgeType, NodeType, validate_edge, validate_node


log = get_logger("graph.neo4j")


class Neo4jAdapter:
    def __init__(self) -> None:
        self._driver: AsyncDriver | None = None

    async def _drv(self) -> AsyncDriver:
        if self._driver is None:
            self._driver = AsyncGraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        return self._driver

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def ensure_constraints(self) -> None:
        statements = [
            # universal id index per label keeps MERGE cheap
            f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:`{nt.value}`) REQUIRE n.id IS UNIQUE"
            for nt in NodeType
        ]
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            for stmt in statements:
                await s.run(stmt)

    async def upsert_node(
        self,
        *,
        node_type: NodeType,
        node_id: str,
        props: dict[str, Any],
    ) -> None:
        validate_node(node_type, props)
        props = {**props, "id": node_id, "node_type": node_type.value}
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            await s.run(
                f"MERGE (n:`{node_type.value}` {{id: $id}}) "
                f"SET n += $props",
                id=node_id,
                props=props,
            )

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
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            await s.run(
                f"MATCH (s:`{src_type.value}` {{id: $sid}}), (d:`{dst_type.value}` {{id: $did}}) "
                f"MERGE (s)-[r:`{edge_type.value}`]->(d) "
                f"SET r += $props",
                sid=src_id,
                did=dst_id,
                props=props,
            )

    async def get_node(self, node_id: str) -> dict[str, Any] | None:
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run("MATCH (n {id: $id}) RETURN n LIMIT 1", id=node_id)
            rec = await res.single()
            return dict(rec["n"]) if rec else None

    async def find_nodes(
        self,
        *,
        node_type: str | None = None,
        props: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        props = props or {}
        label = f":`{node_type}`" if node_type else ""
        where = " AND ".join(f"toLower(toString(n.{k})) = toLower($p_{k})" for k in props)
        cypher = f"MATCH (n{label}) {'WHERE ' + where if where else ''} RETURN n LIMIT $limit"
        params = {f"p_{k}": v for k, v in props.items()}
        params["limit"] = limit
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run(cypher, **params)
            return [dict(rec["n"]) async for rec in res]

    async def lookup_case_by_citation(self, citation: str) -> str | None:
        drv = await self._drv()
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run(
                "MATCH (c:Case) WHERE any(x IN coalesce(c.citations, []) "
                "WHERE toLower(x) = toLower($q)) RETURN c.id AS id LIMIT 1",
                q=citation,
            )
            rec = await res.single()
            return rec["id"] if rec else None

    async def neighbors(
        self,
        node_id: str,
        *,
        edge_types: tuple[str, ...] | None = None,
        direction: str = "any",
    ) -> list[dict[str, Any]]:
        if direction == "out":
            pattern = "(n {id: $id})-[r]->(m)"
        elif direction == "in":
            pattern = "(n {id: $id})<-[r]-(m)"
        else:
            pattern = "(n {id: $id})-[r]-(m)"
        filt = ""
        if edge_types:
            filt = "WHERE type(r) IN $types"
        cypher = (
            f"MATCH {pattern} {filt} "
            "RETURN m AS node, type(r) AS edge_type, "
            "CASE WHEN startNode(r).id = $id THEN 'out' ELSE 'in' END AS edge_direction, "
            "properties(r) AS edge_props LIMIT 1000"
        )
        drv = await self._drv()
        params: dict[str, Any] = {"id": node_id}
        if edge_types:
            params["types"] = list(edge_types)
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run(cypher, **params)
            out: list[dict[str, Any]] = []
            async for rec in res:
                out.append(
                    {
                        "edge_type": rec["edge_type"],
                        "edge_direction": rec["edge_direction"],
                        "edge_props": dict(rec["edge_props"] or {}),
                        "node": dict(rec["node"]),
                    }
                )
            return out

    async def get_span_for_node(self, node_id: str) -> dict[str, Any] | None:
        """Return the best-available SourceSpan backing a node or edge uuid.

        Four-tier lookup so both typed LexGraph nodes and Graphiti-sourced
        Entity nodes / EntityEdges resolve to provenance:

        1. **Direct edge** — Paragraph/Section/etc. have
           ``NODE_DERIVED_FROM_SOURCE`` to their backing SourceSpan.
        2. **Entity via Episodic** — Graphiti ``Entity`` uuids aren't written
           as ``.id``; they're connected by ``Episodic-[:MENTIONS]->Entity``.
           The Episodic's ``source_description`` is encoded as
           ``provenance_span:<span_id>``, so parse that and fetch the
           SourceSpan.
        3. **EntityEdge via endpoint Entities** — ``EntityEdge`` uuids are
           attached to ``RELATES_TO`` relationships, not nodes. We walk both
           endpoints of the ``RELATES_TO`` whose ``uuid = $id`` into an
           Episodic and resolve its SourceSpan the same way.
        4. **Synthetic from Episodic** — if the referenced SourceSpan is
           missing, still return a dict carrying Episodic content so the
           generator has at least the fact/paragraph text to quote.
        """
        drv = await self._drv()
        # Collect Episodic candidates via three independent paths, then pick
        # the best-backed SourceSpan (prefer a direct NODE_DERIVED_FROM_SOURCE
        # edge, else the Episodic that mentions the entity / anchors the
        # relation, else synthesise from Episodic.content).
        cypher = (
            "OPTIONAL MATCH (n) WHERE n.id = $id OR n.uuid = $id "
            "WITH n LIMIT 1 "
            # Path A: direct provenance on typed nodes (Paragraph, Section, ...)
            "OPTIONAL MATCH (n)-[:`NODE_DERIVED_FROM_SOURCE`]->(direct:SourceSpan) "
            # Path B: Graphiti Entity uuid -> Episodic that MENTIONS it
            "OPTIONAL MATCH (n)<-[:MENTIONS]-(ep_n:Episodic) "
            # Path C: Graphiti EntityEdge uuid sits on a RELATES_TO edge; walk
            # to both endpoints and find the Episodic that mentions either.
            "OPTIONAL MATCH (a:Entity)-[r:RELATES_TO {uuid: $id}]->(b:Entity) "
            "OPTIONAL MATCH (ep_e:Episodic)-[:MENTIONS]->(ee:Entity) "
            "    WHERE r IS NOT NULL AND (ee.uuid = a.uuid OR ee.uuid = b.uuid) "
            "WITH direct, ep_n, collect(DISTINCT ep_e) AS eps_edge "
            "WITH direct, coalesce(ep_n, head(eps_edge)) AS ep "
            "WITH direct, ep, "
            "     CASE WHEN ep.source_description STARTS WITH 'provenance_span:' "
            "          THEN substring(ep.source_description, size('provenance_span:')) "
            "          ELSE NULL END AS sid "
            "OPTIONAL MATCH (via:SourceSpan) WHERE sid IS NOT NULL AND via.id = sid "
            "WITH coalesce(direct, via) AS sp, ep "
            "RETURN sp, ep LIMIT 1"
        )
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run(cypher, id=node_id)
            rec = await res.single()
            if rec is None:
                return None
            sp = rec["sp"]
            if sp is not None:
                return dict(sp)
            ep = rec["ep"]
            if ep is None:
                return None
            # No resolvable SourceSpan — synthesise one from Episodic content
            # so the generator still gets provenance-safe text to quote.
            ep_d = dict(ep)
            return {
                "id": ep_d.get("uuid", ""),
                "text": ep_d.get("content", ""),
                "episode_ref": ep_d.get("uuid", ""),
                "file_ref": "",
                "page": None,
                "char_start": 0,
                "char_end": len(ep_d.get("content", "") or ""),
                "node_type": "SourceSpan",
            }

    async def neighborhood(
        self,
        *,
        seeds: list[str],
        max_hops: int,
        max_nodes: int,
        authority_ceiling: int | None = None,
        matter_scope: str | None = None,
    ) -> dict[str, Any]:
        """Bounded BFS from seed node ids. Returns nodes + edges dicts."""
        drv = await self._drv()
        cypher = (
            "UNWIND $seeds AS sid "
            "MATCH (s {id: sid}) "
            "CALL apoc.path.subgraphAll(s, {"
            "  maxLevel: $max_hops, "
            "  relationshipFilter: '', "
            "  labelFilter: '', "
            "  limit: $max_nodes"
            "}) YIELD nodes, relationships "
            "RETURN nodes, relationships"
        )
        async with drv.session(database=settings.neo4j_database) as s:
            res = await s.run(
                cypher,
                seeds=seeds,
                max_hops=max_hops,
                max_nodes=max_nodes,
            )
            nodes: dict[str, dict[str, Any]] = {}
            edges: list[dict[str, Any]] = []
            async for rec in res:
                for n in rec["nodes"]:
                    node = dict(n)
                    tier = node.get("authority_tier")
                    if authority_ceiling is not None and tier is not None and tier > authority_ceiling:
                        continue
                    if matter_scope is not None:
                        # exclude private nodes outside scope
                        mscope = node.get("matter_id")
                        if mscope and mscope != matter_scope:
                            continue
                    nodes[node.get("id", node.get("elementId"))] = node
                for r in rec["relationships"]:
                    edges.append(
                        {
                            "type": r.type,
                            "src": r.start_node.get("id"),
                            "dst": r.end_node.get("id"),
                            "props": dict(r),
                        }
                    )
        return {"nodes": nodes, "edges": edges}
