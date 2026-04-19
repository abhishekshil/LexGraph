"""Assemble the :class:`EvidencePack` that the generator will consume.

Responsibilities:
  * Turn ranked graph/semantic candidates into typed :class:`EvidenceSpan` rows
    by joining back to the :class:`SourceSpan` of record.
  * Respect the configured *token budget* using a cheap words/4 approximation
    (falls back to tiktoken if present).
  * Enforce *tier diversity* (no single tier dominates unless necessary).
  * Guarantee a *tier-1 anchor* for statute-shaped intents when possible so
    downstream generation always has a binding authority to quote.
  * Detect authority *conflicts* — multiple sources discussing the same
    section/topic from different tiers are surfaced for the UI and for the
    generator's conflict-handling branch.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol

from ..core import get_logger, settings
from ..data_models.evidence import EvidencePack, EvidenceSpan
from ..graph import Neo4jAdapter
from ..ontology.authority import AuthorityTier
from .intent import QueryIntent


log = get_logger("retrieval.evidence")


_STATUTE_INTENTS = {
    QueryIntent.STATUTE_LOOKUP,
    QueryIntent.OFFENCE_INGREDIENT,
    QueryIntent.PUNISHMENT_LOOKUP,
    QueryIntent.PROCEDURE_LOOKUP,
    QueryIntent.EVIDENCE_RULE_LOOKUP,
    QueryIntent.CROSSWALK,
}


class _GraphStoreProto(Protocol):
    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...
    async def get_span_for_node(self, node_id: str) -> dict[str, Any] | None: ...


class EvidenceBuilder:
    def __init__(self, store: _GraphStoreProto | None = None) -> None:
        self.store: _GraphStoreProto = store or Neo4jAdapter()

    async def build(
        self,
        *,
        query: str,
        query_type: str,
        ranked_nodes: list[dict[str, Any]],
        graph_paths: list[list[str]],
        matter_scope: str | None,
    ) -> EvidencePack:
        intent = _intent_from(query_type)

        spans: list[EvidenceSpan] = []
        token_budget = settings.evidence_max_tokens
        max_spans = settings.evidence_max_spans
        tier_cap = max(1, settings.evidence_tier_cap)

        tier_counts: dict[int, int] = defaultdict(int)
        tokens_spent = 0

        # First pass: take best candidates while honouring the tier cap. This
        # stops a single tier (e.g. AI summaries) dominating the pack.
        for i, node in enumerate(ranked_nodes):
            if len(spans) >= max_spans:
                break
            tier = int(node.get("authority_tier", AuthorityTier.AI_SUMMARY))
            if tier_counts[tier] >= tier_cap:
                continue
            span = await self._materialise(node, marker=f"S{len(spans) + 1}")
            if span is None:
                continue
            cost = _approx_tokens(span.excerpt)
            if tokens_spent + cost > token_budget and spans:
                break
            tokens_spent += cost
            tier_counts[tier] += 1
            spans.append(span)

        # Second pass: if statutory intent has no tier-1 anchor, try to add one
        # even if the tier cap is saturated elsewhere.
        if (
            settings.evidence_force_tier1_for_statute
            and intent in _STATUTE_INTENTS
            and not any(int(s.tier) == int(AuthorityTier.CONSTITUTION_STATUTE) for s in spans)
        ):
            for node in ranked_nodes:
                if int(node.get("authority_tier", 9)) != int(AuthorityTier.CONSTITUTION_STATUTE):
                    continue
                span = await self._materialise(node, marker=f"S{len(spans) + 1}")
                if span is None:
                    continue
                cost = _approx_tokens(span.excerpt)
                if tokens_spent + cost > token_budget and spans:
                    # evict the lowest-tier span to make room
                    if not _evict_lowest_tier(spans):
                        break
                    tokens_spent = sum(_approx_tokens(s.excerpt) for s in spans)
                spans.append(span)
                tokens_spent += cost
                break

        # Renumber markers so they remain dense (S1..Sn in order of use).
        for i, s in enumerate(spans, start=1):
            s.marker = f"S{i}"

        conflicts = _detect_conflicts(spans)
        sufficient = bool(spans) and (
            intent not in _STATUTE_INTENTS
            or any(int(s.tier) <= int(AuthorityTier.HIGH_COURT) for s in spans)
        )
        confidence = _confidence_from(spans, intent=intent)

        pack = EvidencePack(
            query=query,
            query_type=query_type,
            intent={},
            spans=spans,
            graph_paths=graph_paths[: settings.evidence_max_spans],
            conflicts=conflicts,
            matter_scope=matter_scope,
            confidence=confidence,
            insufficient_evidence=not sufficient,
            retrieval_debug={
                "ranked_in": len(ranked_nodes),
                "ranked_used": len(spans),
                "tokens_spent": tokens_spent,
                "tier_counts": dict(tier_counts),
            },
        )
        log.info(
            "evidence.built",
            spans=len(spans),
            insufficient=pack.insufficient_evidence,
            conflicts=len(conflicts),
            tier_counts=dict(tier_counts),
        )
        return pack

    async def _materialise(
        self,
        node: dict[str, Any],
        *,
        marker: str,
    ) -> EvidenceSpan | None:
        nid = node.get("id")
        if not nid:
            return None
        node_type = node.get("node_type") or "Unknown"
        # Infrastructure nodes (File / Episode / raw SourceSpan) are not
        # evidence themselves — they back other typed nodes. Skip them so the
        # pack stays semantically meaningful.
        if node_type in {"File", "SourceEpisode"}:
            return None
        if node_type == "SourceSpan":
            # Treat the source span itself as its own evidence row so we never
            # lose provenance. This is rare but happens when a seed surfaced a
            # span via semantic fallback.
            sp = dict(node)
        else:
            try:
                sp = await self.store.get_span_for_node(str(nid))
            except Exception as e:  # noqa: BLE001
                log.warning("evidence.span_lookup_failed", node=nid, error=str(e))
                sp = None
        if not sp:
            # Fall back to the semantic-fallback excerpt if we have no graph
            # provenance (e.g. the candidate came from Qdrant only).
            excerpt = str(node.get("excerpt") or node.get("text") or "")
            if not excerpt.strip():
                return None
            return _span_from_node(node, marker=marker, excerpt=excerpt)

        excerpt = str(sp.get("text", ""))[:1200]
        tier_val = node.get("authority_tier") or int(AuthorityTier.AI_SUMMARY)
        kind = "private" if node.get("matter_id") else "public"
        return EvidenceSpan(
            marker=marker,
            node_id=str(nid),
            node_type=str(node_type),
            source_span_id=str(sp.get("id", node.get("source_span_id", ""))),
            source_episode_id=str(sp.get("episode_ref") or sp.get("episode_id") or ""),
            file_id=str(sp.get("file_ref") or sp.get("file_id") or ""),
            title=node.get("title") or node.get("short_title") or node.get("heading"),
            citation=node.get("citation"),
            section_or_paragraph=_label_for(node),
            court=node.get("court"),
            date=node.get("decision_date") or node.get("date"),
            excerpt=excerpt,
            page=sp.get("page"),
            char_start=int(sp.get("char_start", 0)),
            char_end=int(sp.get("char_end", len(excerpt))),
            tier=AuthorityTier(int(tier_val)),
            score=float(node.get("score", 0.0)),
            kind=kind,  # type: ignore[arg-type]
            matter_id=node.get("matter_id"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _intent_from(query_type: str) -> QueryIntent:
    try:
        return QueryIntent(query_type)
    except ValueError:
        return QueryIntent.GENERIC


def _span_from_node(node: dict[str, Any], *, marker: str, excerpt: str) -> EvidenceSpan:
    tier_val = node.get("authority_tier") or int(AuthorityTier.AI_SUMMARY)
    return EvidenceSpan(
        marker=marker,
        node_id=str(node.get("id")),
        node_type=str(node.get("node_type") or "Unknown"),
        source_span_id=str(node.get("source_span_id", "")),
        source_episode_id=str(node.get("episode_id", "")),
        file_id=str(node.get("file_id", "")),
        title=node.get("title") or node.get("heading"),
        citation=node.get("citation"),
        section_or_paragraph=_label_for(node),
        court=node.get("court"),
        date=node.get("date"),
        excerpt=excerpt[:1200],
        page=None,
        char_start=0,
        char_end=len(excerpt),
        tier=AuthorityTier(int(tier_val)),
        score=float(node.get("score", 0.0)),
        kind="private" if node.get("matter_id") else "public",
        matter_id=node.get("matter_id"),
    )


def _label_for(node: dict[str, Any]) -> str | None:
    nt = (node.get("node_type") or "").lower()
    if "section" in nt:
        num = node.get("number")
        act = node.get("act_ref") or node.get("act_name") or ""
        if num:
            return f"Section {num} {act}".strip()
        if node.get("section_ref"):
            return str(node["section_ref"])
    if "paragraph" in nt and node.get("number"):
        return f"para {node['number']}"
    if node.get("section_ref"):
        return str(node["section_ref"])
    return None


def _approx_tokens(text: str) -> int:
    if not text:
        return 0
    try:
        import tiktoken  # type: ignore

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:  # noqa: BLE001
        # GPT-ish token ≈ 4 chars or 0.75 words. Take the larger of the two
        # so we don't underestimate on prose-heavy spans.
        return max(1, len(text) // 4, int(len(text.split()) * 0.8))


def _evict_lowest_tier(spans: list[EvidenceSpan]) -> bool:
    if not spans:
        return False
    worst_idx = max(range(len(spans)), key=lambda i: (int(spans[i].tier), -spans[i].score))
    del spans[worst_idx]
    return True


def _confidence_from(spans: list[EvidenceSpan], *, intent: QueryIntent) -> str:
    if not spans:
        return "low"
    tiers = sorted(int(s.tier) for s in spans)
    top = tiers[:3]
    avg = sum(top) / len(top)
    has_tier1 = tiers[0] == int(AuthorityTier.CONSTITUTION_STATUTE)
    if intent in _STATUTE_INTENTS and not has_tier1:
        return "low"
    if avg <= 2.5 and len(spans) >= 2:
        return "high"
    if avg <= 4.5:
        return "medium"
    return "low"


def _detect_conflicts(spans: list[EvidenceSpan]) -> list[dict[str, Any]]:
    """Multiple authorities discussing the same section/label at different
    tiers are flagged. Lower (better) tier wins; the conflict is surfaced for
    the UI and the generator."""
    conflicts: list[dict[str, Any]] = []
    by_key: dict[str, list[EvidenceSpan]] = defaultdict(list)
    for s in spans:
        key = (s.section_or_paragraph or s.citation or s.title or "").strip().lower()
        if key:
            by_key[key].append(s)
    for key, group in by_key.items():
        if len(group) < 2:
            continue
        tiers = sorted({int(s.tier) for s in group})
        if len(tiers) <= 1:
            continue
        if min(tiers) > int(AuthorityTier.HIGH_COURT):
            # Only worth surfacing when at least one authority is binding.
            continue
        conflicts.append(
            {
                "topic": key,
                "tiers": tiers,
                "description": (
                    f"Multiple authorities on '{key}' across tiers {tiers}; "
                    f"the lower (stronger) tier binds."
                ),
                "markers": [s.marker for s in group],
            }
        )
    return conflicts
