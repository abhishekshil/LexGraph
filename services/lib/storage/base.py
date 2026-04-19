"""Object-store interface shared by MinIO and local backends."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
_DOTRUN = re.compile(r"\.{2,}")


def _sanitise(value: str) -> str:
    """Replace unsafe chars with ``_`` and collapse '..' runs to defeat path
    traversal. Leading/trailing dots are also stripped."""
    cleaned = _UNSAFE.sub("_", value.strip())
    cleaned = _DOTRUN.sub("_", cleaned)
    return cleaned.strip("._") or ""


def _safe_filename(name: str) -> str:
    base = _sanitise(name) or "file"
    return base[:160]


@dataclass(frozen=True, slots=True)
class ObjectKey:
    """Bucket + key pair. ``uri`` renders as ``s3://bucket/key``."""

    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def storage_key_for(
    *,
    prefix: str,
    sha256: str,
    filename: str,
) -> str:
    """Deterministic key: ``<prefix>/<sha[0:2]>/<sha[2:4]>/<sha[0:12]>_<safe>``.

    Using the hash as the primary segment means two uploads of the same bytes
    never clobber each other and we can verify integrity at read time without
    a round-trip to a metadata store.
    """
    safe_prefix = _sanitise(prefix.strip("/")) or "unscoped"
    return f"{safe_prefix}/{sha256[0:2]}/{sha256[2:4]}/{sha256[0:12]}_{_safe_filename(filename)}"


class ObjectStore(Protocol):
    """Narrow async interface. Any backend implementing this works everywhere."""

    async def ensure_bucket(self, bucket: str) -> None: ...

    async def put_object(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> ObjectKey: ...

    async def get_object(self, bucket: str, key: str) -> bytes: ...

    async def exists(self, bucket: str, key: str) -> bool: ...

    async def presign_get(
        self,
        bucket: str,
        key: str,
        *,
        expires_s: int = 3600,
    ) -> str: ...

    async def close(self) -> None: ...
