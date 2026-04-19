"""End-to-end retrieval: classify → seeds → typed BFS → fallback → rerank → pack.

The orchestrator is backend-agnostic. Pass an :class:`InMemoryGraphStore` in
tests; in production the default :class:`Neo4jAdapter` is used.
"""

from __future__ import annotations

from typing import Any, Protocol

from ..core import get_logger, settings
from ..data_models.evidence import EvidencePack
from ..graph import Neo4jAdapter
from ..observability import emit_step
from ..reranking import CompositeReranker
from .evidence_builder import EvidenceBuilder
from .graph_retriever import GraphRetriever
from .intent import QueryIntent, classify_intent
from .seeds import find_seed_nodes
from .semantic_fallback import SemanticFallback


log = get_logger("retrieval.orchestrator")


class _StoreProto(Protocol):
    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...
    async def neighbors(self, node_id: str, *, edge_types: tuple[str, ...] | None = None,
                        direction: str = "any") -> list[dict[str, Any]]: ...
    async def find_nodes(self, *, node_type: str | None = None,
                         props: dict[str, Any] | None = None,
                         limit: int = 10) -> list[dict[str, Any]]: ...
    async def lookup_case_by_citation(self, citation: str) -> str | None: ...
    async def get_span_for_node(self, node_id: str) -> dict[str, Any] | None: ...


class RetrievalOrchestrator:
    def __init__(
        self,
        *,
        store: _StoreProto | None = None,
        semantic: SemanticFallback | None = None,
        reranker: CompositeReranker | None = None,
    ) -> None:
        self.store: _StoreProto = store or Neo4jAdapter()
        self.graph_retriever = GraphRetriever(self.store)
        self.semantic = semantic or SemanticFallback()
        self.reranker = reranker or CompositeReranker()
        self.evidence = EvidenceBuilder(self.store)

    async def answer(
        self,
        *,
        question: str,
        matter_scope: str | None = None,
        mode: str | None = None,
        as_of: str | None = None,
    ) -> EvidencePack:
        mode = mode or settings.retrieval_mode

        await emit_step(
            "intent.classify",
            status="start",
            worker="retrieve",
            message="Classifying query intent",
        )
        intent = classify_intent(question, has_matter=bool(matter_scope))
        await emit_step(
            "intent.classify",
            status="done",
            worker="retrieve",
            message=f"Intent: {intent.intent.value}",
            intent=intent.intent.value,
            signals=intent.signals,
        )

        await emit_step(
            "seeds.find",
            status="start",
            worker="retrieve",
            message="Finding seed nodes (sections, citations, acts, entities)",
        )
        seeds = await find_seed_nodes(
            question,
            store=self.store,
            matter_scope=matter_scope,
            semantic_seed=self.semantic,
        )
        await emit_step(
            "seeds.find",
            status="done",
            worker="retrieve",
            message=f"{len(seeds.node_ids)} seed node(s)",
            count=len(seeds.node_ids),
            reasons=seeds.reasons[:12],
            node_ids=seeds.node_ids[:12],
        )

        await emit_step(
            "graph.retrieve",
            status="start",
            worker="retrieve",
            message="Running typed BFS + Graphiti semantic graph search",
            seeds=len(seeds.node_ids),
        )
        graph_result = await self.graph_retriever.retrieve(
            query=question,
            seeds=seeds.node_ids,
            intent=intent.intent,
            matter_scope=matter_scope,
            as_of=as_of,
        )
        await emit_step(
            "graph.retrieve",
            status="done",
            worker="retrieve",
            message=f"{len(graph_result.nodes)} node(s), {len(graph_result.paths)} path(s)",
            nodes=len(graph_result.nodes),
            paths=len(graph_result.paths),
            sample_nodes=[
                {
                    "id": nid,
                    "type": n.get("node_type"),
                    "tier": n.get("authority_tier"),
                    "source": n.get("source") or n.get("retrieval_source"),
                    "name": n.get("name") or n.get("title"),
                }
                for nid, n in list(graph_result.nodes.items())[:8]
            ],
        )

        candidates: dict[str, dict[str, Any]] = {}
        for nid, node in graph_result.nodes.items():
            candidates[nid] = {**node, "id": nid, "retrieval_source": "graph"}

        if mode != "graph_only":
            await emit_step(
                "semantic.recall",
                status="start",
                worker="retrieve",
                message="Vector recall from Qdrant (semantic fallback)",
            )
            sem_hits = await self.semantic.recall(
                query=question,
                matter_scope=matter_scope,
            )
            for h in sem_hits:
                existing = candidates.get(h.node_id)
                if existing:
                    existing["semantic_score"] = max(
                        float(existing.get("semantic_score", 0.0)), h.score
                    )
                    existing["excerpt"] = existing.get("excerpt") or h.excerpt
                    continue
                candidates[h.node_id] = {
                    "id": h.node_id,
                    "node_type": h.node_type or "SummaryNode",
                    "authority_tier": h.authority_tier,
                    "semantic_score": h.score,
                    "excerpt": h.excerpt,
                    "title": h.title,
                    "section_ref": h.section_ref,
                    "case_ref": h.case_ref,
                    "source_span_id": h.source_span_id,
                    "matter_id": h.matter_id,
                    "retrieval_source": "semantic",
                }
            await emit_step(
                "semantic.recall",
                status="done",
                worker="retrieve",
                message=f"{len(sem_hits)} vector hit(s)",
                hits=len(sem_hits),
            )

        candidate_list = list(candidates.values())

        await emit_step(
            "rerank",
            status="start",
            worker="retrieve",
            message=f"Ranking {len(candidate_list)} candidate(s) "
            f"({'composite rerank' if mode == 'graph_plus_semantic_plus_rerank' else 'default sort'})",
            strategy=mode,
        )
        if mode == "graph_plus_semantic_plus_rerank":
            ranked = self.reranker.rank(question, candidate_list)
        else:
            ranked = _default_sort(candidate_list)

        ranked = ranked[: settings.rerank_topk]
        await emit_step(
            "rerank",
            status="done",
            worker="retrieve",
            message=f"Top-{len(ranked)} selected",
            kept=len(ranked),
        )

        await emit_step(
            "evidence.build",
            status="start",
            worker="retrieve",
            message="Materialising SourceSpans and assembling EvidencePack",
        )
        pack = await self.evidence.build(
            query=question,
            query_type=intent.intent.value,
            ranked_nodes=ranked,
            graph_paths=graph_result.paths,
            matter_scope=matter_scope,
        )
        await emit_step(
            "evidence.build",
            status="done",
            worker="retrieve",
            message=(
                "Insufficient evidence" if pack.insufficient_evidence
                else f"{len(pack.spans)} span(s) in pack"
            ),
            spans=len(pack.spans),
            insufficient=pack.insufficient_evidence,
            markers=[s.marker for s in pack.spans[:12]],
        )
        pack.intent = {
            "class": intent.intent.value,
            "signals": intent.signals,
            "seed_reasons": seeds.reasons,
            "mode": mode,
        }
        log.info(
            "retrieval.done",
            intent=intent.intent.value,
            seeds=len(seeds.node_ids),
            candidates=len(candidate_list),
            ranked=len(ranked),
            spans=len(pack.spans),
        )
        return pack


def _default_sort(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _key(c: dict[str, Any]) -> tuple[int, float, float]:
        tier = int(c.get("authority_tier", 8))
        sem = -float(c.get("semantic_score", 0.0))
        base = -float(c.get("score", 0.0))
        return (tier, base, sem)

    return sorted(candidates, key=_key)
