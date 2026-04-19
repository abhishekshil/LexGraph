"""Async wrapper over qdrant-client.

Two collections are maintained:
  - ``lex_public``  — public corpus (statutes, case law, rules, circulars)
  - ``lex_private`` — one logical collection that stores all private-matter
                      points tagged with ``matter_id``; retrieval filters by
                      matter to enforce isolation.

If qdrant-client or a live Qdrant instance is unavailable, an in-memory
fallback implementation is used. This keeps the whole pipeline runnable in
tests and on laptops; production deploys set ``QDRANT_URL``.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import threading
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Iterable

from ..core import get_logger, settings
from .embedder import Embedder, get_embedder
from .payload import IndexPayload, payload_to_dict


log = get_logger("indexing.qdrant")


@dataclass
class IndexHit:
    node_id: str
    score: float
    payload: dict[str, Any]


class QdrantIndexer:
    """Thin async facade. All blocking calls run on a thread pool."""

    def __init__(self, embedder: Embedder | None = None) -> None:
        self._embedder = embedder or get_embedder()
        self._client = None
        self._fallback: _InMemoryIndex | None = None
        self._ensured: set[str] = set()
        self._lock = threading.Lock()

    # ---- public API ----------------------------------------------------

    async def ensure_collection(self, *, name: str) -> None:
        if name in self._ensured:
            return
        c = self._client_or_fallback()
        if isinstance(c, _InMemoryIndex):
            c.ensure(name)
            self._ensured.add(name)
            return

        def _run() -> None:
            from qdrant_client.http.models import Distance, VectorParams  # type: ignore

            existing = {col.name for col in c.get_collections().collections}
            if name in existing:
                return
            c.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=self._embedder.dim, distance=Distance.COSINE),
            )

        try:
            await asyncio.to_thread(_run)
            self._ensured.add(name)
        except Exception as e:  # noqa: BLE001
            log.warning("qdrant.ensure_failed_falling_back", collection=name, error=str(e))
            self._switch_to_fallback()
            await self.ensure_collection(name=name)

    async def upsert(self, *, collection: str, payloads: Iterable[IndexPayload]) -> int:
        items = list(payloads)
        if not items:
            return 0
        await self.ensure_collection(name=collection)

        texts = [_index_text(p) for p in items]
        vectors = await asyncio.to_thread(self._embedder.encode, texts)

        c = self._client_or_fallback()
        if isinstance(c, _InMemoryIndex):
            for p, v in zip(items, vectors):
                c.upsert(collection, _point_id(p.node_id), v, payload_to_dict(p))
            return len(items)

        def _run() -> int:
            from qdrant_client.http.models import PointStruct  # type: ignore

            points = [
                PointStruct(id=_point_id(p.node_id), vector=v, payload=payload_to_dict(p))
                for p, v in zip(items, vectors)
            ]
            c.upsert(collection_name=collection, points=points, wait=False)
            return len(points)

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:  # noqa: BLE001
            log.warning("qdrant.upsert_failed_falling_back", error=str(e))
            self._switch_to_fallback()
            return await self.upsert(collection=collection, payloads=items)

    async def search(
        self,
        *,
        collection: str,
        query: str,
        topk: int,
        matter_id: str | None = None,
        extra_filters: dict[str, Any] | None = None,
    ) -> list[IndexHit]:
        if not query:
            return []
        await self.ensure_collection(name=collection)
        vec = await asyncio.to_thread(self._embedder.encode_one, query)
        if not vec:
            return []

        c = self._client_or_fallback()
        if isinstance(c, _InMemoryIndex):
            return c.search(collection, vec, topk, matter_id=matter_id, extras=extra_filters)

        def _run() -> list[IndexHit]:
            flt = _build_filter(matter_id=matter_id, extras=extra_filters)
            res = c.search(
                collection_name=collection,
                query_vector=vec,
                limit=topk,
                query_filter=flt,
                with_payload=True,
            )
            out: list[IndexHit] = []
            for h in res:
                payload = dict(h.payload or {})
                nid = payload.get("node_id")
                if not nid:
                    continue
                out.append(IndexHit(node_id=str(nid), score=float(h.score), payload=payload))
            return out

        try:
            return await asyncio.to_thread(_run)
        except Exception as e:  # noqa: BLE001
            log.warning("qdrant.search_failed_falling_back", error=str(e))
            self._switch_to_fallback()
            return await self.search(
                collection=collection,
                query=query,
                topk=topk,
                matter_id=matter_id,
                extra_filters=extra_filters,
            )

    def collection_for(self, *, matter_id: str | None) -> str:
        return (
            settings.qdrant_collection_private
            if matter_id
            else settings.qdrant_collection_public
        )

    # ---- internal ------------------------------------------------------

    def _client_or_fallback(self):
        if self._fallback is not None:
            return self._fallback
        if self._client is not None:
            return self._client
        with self._lock:
            if self._fallback is not None:
                return self._fallback
            if self._client is not None:
                return self._client
            try:
                from qdrant_client import QdrantClient  # type: ignore

                self._client = QdrantClient(url=settings.qdrant_url, timeout=5.0)
                # Trip the wire once so we detect a down server immediately.
                self._client.get_collections()
                log.info("qdrant.connected", url=settings.qdrant_url)
                return self._client
            except Exception as e:  # noqa: BLE001
                log.warning("qdrant.unavailable_using_memory", error=str(e))
                self._switch_to_fallback()
                return self._fallback

    def _switch_to_fallback(self) -> None:
        self._fallback = _InMemoryIndex()
        self._client = None
        self._ensured.clear()


@lru_cache
def get_indexer() -> QdrantIndexer:
    return QdrantIndexer()


# ---- helpers ----------------------------------------------------------

def _index_text(p: IndexPayload) -> str:
    head = p.title or p.section_ref or p.citation or ""
    body = p.text
    return (f"{head}\n{body}" if head else body)[:2048]


def _point_id(node_id: str) -> int:
    # Qdrant point ids must be uint or uuid. Hash to 63-bit uint.
    return int.from_bytes(hashlib.sha1(node_id.encode("utf-8")).digest()[:8], "big") >> 1


def _build_filter(*, matter_id: str | None, extras: dict[str, Any] | None):
    try:
        from qdrant_client.http.models import FieldCondition, Filter, MatchValue  # type: ignore
    except Exception:  # noqa: BLE001
        return None
    must = []
    if matter_id:
        must.append(FieldCondition(key="matter_id", match=MatchValue(value=matter_id)))
    else:
        # Public lookups must NOT leak private points. Public collection already
        # excludes them; but when callers re-use a single collection we enforce.
        must.append(FieldCondition(key="matter_id", match=MatchValue(value="__public__")))
    if extras:
        for k, v in extras.items():
            must.append(FieldCondition(key=k, match=MatchValue(value=v)))
    return Filter(must=must) if must else None


# ---- pure-python fallback ---------------------------------------------

class _InMemoryIndex:
    """Plain dict-backed cosine-similarity index for tests & degraded mode."""

    def __init__(self) -> None:
        self._collections: dict[str, list[tuple[int, list[float], dict[str, Any]]]] = {}

    def ensure(self, name: str) -> None:
        self._collections.setdefault(name, [])

    def upsert(self, name: str, pid: int, vec: list[float], payload: dict[str, Any]) -> None:
        pts = self._collections.setdefault(name, [])
        for i, (existing_id, _, _) in enumerate(pts):
            if existing_id == pid:
                pts[i] = (pid, vec, payload)
                return
        pts.append((pid, vec, payload))

    def search(
        self,
        name: str,
        qvec: list[float],
        topk: int,
        *,
        matter_id: str | None,
        extras: dict[str, Any] | None,
    ) -> list[IndexHit]:
        pts = self._collections.get(name, [])
        if not pts:
            return []
        results: list[IndexHit] = []
        for pid, v, payload in pts:
            if matter_id is not None and payload.get("matter_id") != matter_id:
                continue
            if matter_id is None and payload.get("matter_id"):
                # public collection / public search must skip private leakage
                continue
            if extras:
                skip = False
                for k, ev in extras.items():
                    if payload.get(k) != ev:
                        skip = True
                        break
                if skip:
                    continue
            score = _cosine(qvec, v)
            nid = payload.get("node_id")
            if not nid:
                continue
            results.append(IndexHit(node_id=str(nid), score=score, payload=payload))
        results.sort(key=lambda h: -h.score)
        return results[:topk]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)
