"""Graphiti client wrapper.

Graphiti is the primary temporal-knowledge-graph engine. We wrap it behind a
small interface so the rest of the system only depends on our types, not on
Graphiti internals. That also lets us stub the engine out in unit tests.

NOTE: The real `graphiti_core` package exposes an async `Graphiti` class that
takes Neo4j credentials and an LLM/embedder config. We lazy-import it to keep
the rest of the codebase importable in test environments without the heavy
deps installed.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
from typing import Any

from ..core import get_logger, settings


log = get_logger("graph.graphiti")


class GraphitiClient:
    """Minimal facade over graphiti_core.Graphiti."""

    def __init__(self) -> None:
        self._impl: Any | None = None
        self._lock = asyncio.Lock()

    async def _ensure(self) -> Any:
        if self._impl is not None:
            return self._impl
        async with self._lock:
            if self._impl is not None:
                return self._impl
            try:
                from graphiti_core import Graphiti  # type: ignore
            except Exception as e:  # noqa: BLE001
                log.warning("graphiti_unavailable", error=str(e))
                self._impl = _NullGraphiti()
                return self._impl

            # Also fall back to null mode if Graphiti can't reach Neo4j; this
            # lets tests and air-gapped dev runs exercise the pipeline without
            # requiring the full stack.
            try:
                g = Graphiti(
                    uri=settings.neo4j_uri,
                    user=settings.neo4j_user,
                    password=settings.neo4j_password,
                )
                await g.build_indices_and_constraints()
            except Exception as e:  # noqa: BLE001
                log.warning("graphiti_bootstrap_failed", error=str(e))
                self._impl = _NullGraphiti()
                return self._impl

            self._impl = g
            log.info("graphiti.ready", uri=settings.neo4j_uri)
            return self._impl

    async def add_episode(
        self,
        *,
        name: str,
        episode_body: str,
        source_description: str,
        reference_time: Any,
        group_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Wrapper around ``Graphiti.add_episode``.

        ``metadata`` was supported in older Graphiti versions. In newer
        releases it moved out of the public signature; we keep the kw
        argument here for backward compatibility but no longer forward
        it to the driver. The structural graph in ``services.lib.graph.writer``
        carries the authoritative metadata regardless.
        """
        g = await self._ensure()
        return await g.add_episode(
            name=name,
            episode_body=episode_body,
            source_description=source_description,
            reference_time=reference_time,
            group_id=group_id,
        )

    async def search(
        self,
        query: str,
        *,
        group_ids: list[str] | None = None,
        center_node_uuid: str | None = None,
        num_results: int = 20,
    ) -> list[dict[str, Any]]:
        g = await self._ensure()
        return await g.search(
            query=query,
            group_ids=group_ids,
            center_node_uuid=center_node_uuid,
            num_results=num_results,
        )

    async def close(self) -> None:
        if self._impl is not None and hasattr(self._impl, "close"):
            await self._impl.close()


class _NullGraphiti:
    """Used when graphiti_core isn't installed; logs everything and no-ops."""

    async def add_episode(self, **kwargs: Any) -> dict[str, Any]:
        log.warning("graphiti_null.add_episode", **{k: str(v)[:120] for k, v in kwargs.items()})
        return {"node_uuid": f"null_{kwargs.get('name', 'ep')}"}

    async def search(self, **kwargs: Any) -> list[dict[str, Any]]:
        log.warning("graphiti_null.search", **{k: str(v)[:120] for k, v in kwargs.items()})
        return []

    async def close(self) -> None:
        return None


@lru_cache
def get_graphiti() -> GraphitiClient:
    return GraphitiClient()
