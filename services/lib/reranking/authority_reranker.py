"""Re-rank candidates by authority tier, with tie-break on recency + score.

Scoring: 1 / tier  +  0.1 * normalized_semantic  +  0.05 * recency_bonus
"""

from __future__ import annotations

from typing import Any

from ..ontology.authority import AuthorityTier


class AuthorityReranker:
    def rank(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        def score(n: dict[str, Any]) -> float:
            tier = int(n.get("authority_tier", AuthorityTier.AI_SUMMARY))
            sem = float(n.get("semantic_score", 0.0))
            rec = _recency_bonus(n.get("decision_date") or n.get("date"))
            n["score"] = (1.0 / max(tier, 1)) + 0.1 * sem + 0.05 * rec
            return -n["score"]

        return sorted(candidates, key=score)


def _recency_bonus(value: Any) -> float:
    """Crude recency bonus. Newer judgments get up to +1."""
    if not value:
        return 0.0
    try:
        year = int(str(value)[:4])
    except ValueError:
        return 0.0
    if year < 1950:
        return 0.0
    return min(1.0, (year - 1950) / 80.0)
