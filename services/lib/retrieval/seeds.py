"""Identify seed graph nodes for a query.

Seeds are the starting points for bounded graph traversal. We try several
strategies in order and dedupe the results:

  1. Explicit section references                     e.g. "S.302 IPC"
  2. Crosswalk hits (old → new section & vice versa)
  3. Explicit case citations / neutral citations
  4. Act / Code name matches                          e.g. "under BNS"
  5. Named entity seeds (Witness, Party, Exhibit)     e.g. "as per PW-3"
  6. Semantic-index fallback seeds                    (Qdrant top-k node_ids)

Everything is driven through a small ``GraphStore`` protocol (implemented by
``Neo4jAdapter`` and ``InMemoryGraphStore``), so the retrieval stack can be
exercised without a live Neo4j.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from ..core import get_logger, settings
from ..enrichment import extract_citations, extract_section_refs
from ..enrichment.crosswalk_loader import Crosswalk, load_all_crosswalks


log = get_logger("retrieval.seeds")


class GraphStore(Protocol):
    """Minimum surface seeds need."""

    async def get_node(self, node_id: str) -> dict[str, Any] | None: ...

    async def find_nodes(
        self,
        *,
        node_type: str | None = None,
        props: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]: ...

    async def lookup_case_by_citation(self, citation: str) -> str | None: ...


@dataclass
class Seeds:
    node_ids: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def add(self, node_id: str | None, reason: str) -> None:
        if not node_id:
            return
        if node_id in self.node_ids:
            return
        self.node_ids.append(node_id)
        self.reasons.append(reason)


# Synonym table so "IPC" / "Indian Penal Code" resolve to the same act token.
_ACT_SYNONYMS: dict[str, str] = {
    "ipc": "ipc",
    "indian_penal_code": "ipc",
    "bns": "bns",
    "bharatiya_nyaya_sanhita": "bns",
    "crpc": "crpc",
    "cr_pc": "crpc",
    "code_of_criminal_procedure": "crpc",
    "bnss": "bnss",
    "bharatiya_nagarik_suraksha_sanhita": "bnss",
    "iea": "iea",
    "indian_evidence_act": "iea",
    "bsa": "bsa",
    "bharatiya_sakshya_adhiniyam": "bsa",
    "constitution": "constitution",
    "constitution_of_india": "constitution",
}

# "under BNS" / "section X of BNS" — soft act mentions without a section number.
_ACT_MENTION_RE = re.compile(
    r"\b(IPC|BNS|CrPC|BNSS|IEA|BSA|Indian\s+Penal\s+Code|Bharatiya\s+Nyaya\s+Sanhita|"
    r"Code\s+of\s+Criminal\s+Procedure|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita|"
    r"Indian\s+Evidence\s+Act|Bharatiya\s+Sakshya\s+Adhiniyam|Constitution)\b",
    re.IGNORECASE,
)

# Private-matter entity mentions.
_WITNESS_RE = re.compile(r"\b(PW|DW|CW)[-\s]?(\d+)\b", re.IGNORECASE)
_EXHIBIT_RE = re.compile(r"\b(Ex(?:h|hibit)?\.?\s?[A-Z]?-?\d+)\b")


async def find_seed_nodes(
    question: str,
    *,
    store: GraphStore | None = None,
    neo: Any | None = None,   # legacy alias for `store`
    crosswalks: dict[str, Crosswalk] | None = None,
    matter_scope: str | None = None,
    semantic_seed: "SemanticSeedProvider | None" = None,
) -> Seeds:
    """Resolve seed node ids for ``question``.

    ``store`` is preferred; ``neo`` is accepted for backwards-compatibility.
    """
    graph: GraphStore = store or neo  # type: ignore[assignment]
    if graph is None:
        raise ValueError("find_seed_nodes requires a graph store")
    crosswalks = crosswalks or load_all_crosswalks()
    seeds = Seeds()

    # 1 + 2. Explicit section refs and crosswalks.
    for ref in extract_section_refs(question):
        nid = _section_node_id(ref.act, ref.section)
        if nid and await graph.get_node(nid):
            seeds.add(nid, f"section_ref:{ref.raw}")
        # Propagate through crosswalks so old↔new are both seeded.
        await _add_crosswalk_seeds(seeds, graph, ref.act, ref.section, crosswalks)

    # 3. Case citations.
    for cit in extract_citations(question):
        if cit.kind in {"neutral", "reporter", "case_title"}:
            try:
                hit = await graph.lookup_case_by_citation(cit.raw)
            except Exception as e:  # noqa: BLE001
                log.warning("seed.citation_lookup_failed", error=str(e), citation=cit.raw)
                hit = None
            if hit:
                seeds.add(hit, f"citation:{cit.raw}")

    # 4. Soft act mentions (no section number) → seed the Act node itself.
    for m in _ACT_MENTION_RE.finditer(question):
        act_tok = _act_token(m.group(1))
        if not act_tok:
            continue
        act_id = f"act:{act_tok}"
        if await graph.get_node(act_id):
            seeds.add(act_id, f"act_mention:{m.group(1).strip()}")

    # 5. Private-matter entity seeds.
    if matter_scope:
        for m in _WITNESS_RE.finditer(question):
            label = f"{m.group(1).upper()}-{m.group(2)}"
            hits = await graph.find_nodes(
                node_type="Witness", props={"label": label}, limit=3,
            )
            for h in hits:
                if h.get("matter_id") in (None, matter_scope):
                    seeds.add(h.get("id"), f"witness:{label}")
        for m in _EXHIBIT_RE.finditer(question):
            label = m.group(1)
            hits = await graph.find_nodes(
                node_type="Exhibit", props={"label": label}, limit=3,
            )
            for h in hits:
                if h.get("matter_id") in (None, matter_scope):
                    seeds.add(h.get("id"), f"exhibit:{label}")

    # 6. Semantic fallback — only when structural recall is thin.
    if len(seeds.node_ids) < settings.seed_min_before_semantic and semantic_seed is not None:
        try:
            sem_ids = await semantic_seed.propose(question, matter_scope=matter_scope)
        except Exception as e:  # noqa: BLE001
            log.warning("seed.semantic_failed", error=str(e))
            sem_ids = []
        for nid in sem_ids:
            if await graph.get_node(nid):
                seeds.add(nid, "semantic_seed")

    log.info("seeds.resolved", count=len(seeds.node_ids), reasons=seeds.reasons)
    return seeds


class SemanticSeedProvider(Protocol):
    async def propose(self, question: str, *, matter_scope: str | None) -> list[str]: ...


async def _add_crosswalk_seeds(
    seeds: Seeds,
    store: GraphStore,
    act: str,
    section: str | None,
    crosswalks: dict[str, Crosswalk],
) -> None:
    if not section:
        return
    act_key = act.lower().split(",")[0]
    for cw in crosswalks.values():
        src_key = cw.source_act.lower().split(",")[0]
        tgt_key = cw.target_act.lower().split(",")[0]
        if act_key.startswith(src_key):
            for e in cw.lookup_source(section):
                nid = _section_node_id(cw.target_act, e.target_section)
                if nid and await store.get_node(nid):
                    seeds.add(nid, f"crosswalk:{cw.name}:{section}->{e.target_section}")
        elif act_key.startswith(tgt_key):
            for e in cw.lookup_target(section):
                nid = _section_node_id(cw.source_act, e.source_section)
                if nid and await store.get_node(nid):
                    seeds.add(nid, f"crosswalk:{cw.name}:{e.source_section}<-{section}")


def _section_node_id(act_name: str, section: str | None) -> str | None:
    if not section:
        return None
    tok = _act_token(act_name)
    if not tok:
        return None
    return f"section:{tok}:{section.strip().lower()}"


_YEAR_SUFFIX_RE = re.compile(r"_(19|20)\d{2}$")


def _act_token(name: str) -> str | None:
    if not name:
        return None
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    # strip year suffix "… _1860" / "… _2023"
    slug = _YEAR_SUFFIX_RE.sub("", slug)
    if slug in _ACT_SYNONYMS:
        return _ACT_SYNONYMS[slug]
    # Fall back to progressively shorter slugs so "indian_penal_code_x" still
    # resolves to ipc via "indian_penal_code".
    parts = slug.split("_")
    for cut in range(len(parts), 0, -1):
        candidate = "_".join(parts[:cut])
        if candidate in _ACT_SYNONYMS:
            return _ACT_SYNONYMS[candidate]
    return slug
