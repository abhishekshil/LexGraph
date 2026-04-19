"""Object-storage facade.

The rest of the system depends on this narrow interface only. Two backends:

- `MinioObjectStore` — real MinIO/S3 via the `minio` client.
- `LocalObjectStore` — filesystem fallback, used in tests and when
  `MINIO_ENDPOINT` is unset. It still preserves the same key semantics and can
  produce `file://` presigned URLs so the rest of the pipeline stays uniform.

Key schema (both backends):

    <prefix>/<sha256_prefix>/<safe_filename>

where `<prefix>` is the matter id for private docs, or the adapter name for
public docs. The SHA prefix deduplicates identical uploads cheaply.
"""

from __future__ import annotations

from .base import ObjectStore, ObjectKey, storage_key_for
from .factory import ensure_default_buckets, get_object_store

__all__ = [
    "ObjectStore",
    "ObjectKey",
    "ensure_default_buckets",
    "get_object_store",
    "storage_key_for",
]
