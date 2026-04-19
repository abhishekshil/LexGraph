"""MinIO/S3 backed object store.

Uses the sync `minio` Python client underneath but exposes an async interface
by offloading to a threadpool. This avoids pulling in aioboto3 and keeps us
compatible with any S3-compatible store.
"""

from __future__ import annotations

import asyncio
import io
from datetime import timedelta
from typing import Any

from ..core import get_logger


log = get_logger("storage.minio")


class MinioObjectStore:
    """Thin async wrapper around the official MinIO SDK."""

    def __init__(
        self,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
    ) -> None:
        # Lazy-import so environments without the `minio` package can still
        # import `services.lib.storage` (e.g. for unit tests using the local store).
        from minio import Minio  # type: ignore

        self._client: Any = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._buckets_ensured: set[str] = set()

    @staticmethod
    def _is_no_such_bucket(error: Exception) -> bool:
        return getattr(error, "code", None) == "NoSuchBucket" or "NoSuchBucket" in str(error)

    # -- sync helpers executed via thread offload ---------------------------

    def _sync_ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)
            log.info("minio.bucket_created", bucket=bucket)

    def _sync_put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None,
        metadata: dict[str, str] | None,
    ) -> None:
        self._client.put_object(
            bucket,
            key,
            io.BytesIO(data),
            length=len(data),
            content_type=content_type or "application/octet-stream",
            metadata=metadata or None,
        )

    def _sync_get(self, bucket: str, key: str) -> bytes:
        resp = self._client.get_object(bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def _sync_exists(self, bucket: str, key: str) -> bool:
        # stat_object raises on missing objects.
        try:
            self._client.stat_object(bucket, key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _sync_presign(self, bucket: str, key: str, expires_s: int) -> str:
        return self._client.presigned_get_object(
            bucket, key, expires=timedelta(seconds=expires_s)
        )

    # -- async interface ----------------------------------------------------

    async def ensure_bucket(self, bucket: str) -> None:
        if bucket in self._buckets_ensured:
            return
        await asyncio.to_thread(self._sync_ensure_bucket, bucket)
        self._buckets_ensured.add(bucket)

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ):
        from .base import ObjectKey

        await self.ensure_bucket(bucket)
        await asyncio.to_thread(
            self._sync_put, bucket, key, data, content_type, metadata
        )
        return ObjectKey(bucket=bucket, key=key)

    async def get_object(self, bucket: str, key: str) -> bytes:
        try:
            return await asyncio.to_thread(self._sync_get, bucket, key)
        except Exception as e:  # noqa: BLE001
            if not self._is_no_such_bucket(e):
                raise
            log.warning("minio.bucket_missing_on_get", bucket=bucket, key=key)
            await self.ensure_bucket(bucket)
            return await asyncio.to_thread(self._sync_get, bucket, key)

    async def exists(self, bucket: str, key: str) -> bool:
        return await asyncio.to_thread(self._sync_exists, bucket, key)

    async def presign_get(
        self,
        bucket: str,
        key: str,
        *,
        expires_s: int = 3600,
    ) -> str:
        return await asyncio.to_thread(self._sync_presign, bucket, key, expires_s)

    async def close(self) -> None:
        return None
