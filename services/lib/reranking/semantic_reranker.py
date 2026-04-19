"""Cross-encoder reranker with a lexical fallback.

When the BGE / reranker model is available we use it (best quality). When it
isn't (no GPU, no network, CI sandbox) we fall back to a cheap lexical
scorer (token Jaccard + title boost + authority-tier tie-break) so the
pipeline keeps producing sensibly ordered results.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from ..core import get_logger, settings


log = get_logger("rerank.semantic")


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+")


def _tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 2}


def _lexical_score(query_toks: set[str], cand_text: str, title: str | None) -> float:
    if not query_toks:
        return 0.0
    cand = _tokens(cand_text)
    inter = query_toks & cand
    jacc = len(inter) / max(len(query_toks | cand), 1)
    title_toks = _tokens(title or "")
    title_bonus = len(query_toks & title_toks) / max(len(query_toks), 1)
    return 0.7 * jacc + 0.3 * title_bonus


class SemanticReranker:
    def __init__(self) -> None:
        self._model = None            # None=not-tried, False=tried+failed
        self._lock = threading.Lock()

    def _load(self):
        if self._model is False:
            return None
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model if self._model is not False else None
            try:
                from sentence_transformers import CrossEncoder  # type: ignore

                self._model = CrossEncoder(settings.reranker_model)
                log.info("rerank.loaded", model=settings.reranker_model)
            except Exception as e:  # noqa: BLE001
                log.warning("rerank.unavailable_using_lexical", error=str(e))
                self._model = False
                return None
        return self._model

    def rank(self, query: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not candidates:
            return []
        texts = [
            str(c.get("summary") or c.get("excerpt") or c.get("text") or "")[:512]
            for c in candidates
        ]
        titles = [c.get("title") or c.get("heading") or c.get("section_ref") for c in candidates]

        model = self._load()
        if model:
            pairs = list(zip([query] * len(texts), texts))
            try:
                scores = model.predict(pairs)
                for c, s in zip(candidates, scores):
                    c["semantic_score"] = float(s)
                return sorted(candidates, key=lambda c: -float(c.get("semantic_score", 0.0)))
            except Exception as e:  # noqa: BLE001
                log.warning("rerank.runtime_failed_lexical_fallback", error=str(e))

        # Lexical fallback
        q_toks = _tokens(query)
        for c, text, title in zip(candidates, texts, titles):
            c["semantic_score"] = _lexical_score(q_toks, text, title)
        return sorted(candidates, key=lambda c: -float(c.get("semantic_score", 0.0)))
