"""Factory picking the right object store backend based on config."""

from __future__ import annotations

import asyncio
from functools import lru_cache

from ..core import get_logger, settings
from .base import ObjectStore
from .local_store import LocalObjectStore


log = get_logger("storage.factory")


@lru_cache
def get_object_store() -> ObjectStore:
    endpoint = (settings.minio_endpoint or "").strip()
    if not endpoint or settings.app_env == "test":
        from pathlib import Path

        root = Path(settings.data_dir) / "object_store"
        log.info("storage.local", root=str(root))
        return LocalObjectStore(root=root)

    try:
        from .minio_store import MinioObjectStore

        store = MinioObjectStore(
            endpoint=endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        log.info("storage.minio", endpoint=endpoint, secure=settings.minio_secure)
        return store
    except Exception as e:  # noqa: BLE001
        log.warning("storage.minio_unavailable", error=str(e))
        from pathlib import Path

        root = Path(settings.data_dir) / "object_store"
        return LocalObjectStore(root=root)


async def ensure_default_buckets(
    *,
    attempts: int = 5,
    backoff_s: float = 0.25,
) -> None:
    """Bootstrap the configured public/private buckets.

    Compose only waits for the MinIO container to *start*, not for it to become
    ready for bucket operations. A short retry loop avoids a common cold-start
    race where the first storage read/write fails with ``NoSuchBucket`` or a
    transient connection error before any API request has created the buckets.
    """

    store = get_object_store()
    buckets = tuple(
        dict.fromkeys(
            b.strip()
            for b in (
                settings.minio_bucket_public,
                settings.minio_bucket_private,
            )
            if b and b.strip()
        )
    )
    if not buckets:
        return

    for attempt in range(1, attempts + 1):
        try:
            for bucket in buckets:
                await store.ensure_bucket(bucket)
            log.info("storage.buckets_ready", buckets=list(buckets))
            return
        except Exception as e:  # noqa: BLE001
            if attempt == attempts:
                raise
            log.warning(
                "storage.buckets_retry",
                attempt=attempt,
                attempts=attempts,
                error=str(e),
            )
            await asyncio.sleep(backoff_s * attempt)
