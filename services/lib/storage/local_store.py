"""Local filesystem object store.

Useful for:
  - Unit / integration tests (no MinIO container required).
  - Local development when the user has not started the stack.
  - Ingesting into an air-gapped environment.

Key layout on disk:

    <root>/<bucket>/<key>

Presigned URLs render as `file://` paths; these are safe to pass around within
the local process but should NOT be shown to end users when a real store is
available.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from ..core import get_logger


log = get_logger("storage.local")


class LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, bucket: str, key: str) -> Path:
        return self.root / bucket / key

    async def ensure_bucket(self, bucket: str) -> None:
        (self.root / bucket).mkdir(parents=True, exist_ok=True)

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
        p = self._path(bucket, key)
        p.parent.mkdir(parents=True, exist_ok=True)

        def _write() -> None:
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)

        await asyncio.to_thread(_write)
        log.debug("local.put", bucket=bucket, key=key, bytes=len(data))
        return ObjectKey(bucket=bucket, key=key)

    async def get_object(self, bucket: str, key: str) -> bytes:
        p = self._path(bucket, key)
        return await asyncio.to_thread(p.read_bytes)

    async def exists(self, bucket: str, key: str) -> bool:
        return self._path(bucket, key).exists()

    async def presign_get(
        self,
        bucket: str,
        key: str,
        *,
        expires_s: int = 3600,
    ) -> str:
        return f"file://{self._path(bucket, key).resolve()}"

    async def close(self) -> None:
        return None
