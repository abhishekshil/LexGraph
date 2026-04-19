"""Compose semantic + authority reranking."""

from __future__ import annotations

from typing import Any

from .authority_reranker import AuthorityReranker
from .semantic_reranker import SemanticReranker


class CompositeReranker:
    def __init__(self) -> None:
        self.sem = SemanticReranker()
        self.auth = AuthorityReranker()

    def rank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        scored = self.sem.rank(query, candidates)
        return self.auth.rank(scored)
