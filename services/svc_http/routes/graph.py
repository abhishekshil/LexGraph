from __future__ import annotations

from fastapi import APIRouter, Query

from ...lib.core import settings
from ...lib.graph import Neo4jAdapter


router = APIRouter(prefix="/graph", tags=["graph"])


@router.get("/subgraph")
async def subgraph(
    seeds: list[str] = Query(...),
    max_hops: int | None = None,
    max_nodes: int | None = None,
    matter_scope: str | None = None,
):
    neo = Neo4jAdapter()
    sub = await neo.neighborhood(
        seeds=seeds,
        max_hops=max_hops or settings.graph_max_hops,
        max_nodes=max_nodes or settings.graph_max_nodes,
        matter_scope=matter_scope,
    )
    return {"nodes": list(sub["nodes"].values()), "edges": sub["edges"]}
