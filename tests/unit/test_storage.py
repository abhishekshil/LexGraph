from __future__ import annotations

import pytest

from services.lib.storage import storage_key_for
from services.lib.storage.factory import ensure_default_buckets
from services.lib.storage.local_store import LocalObjectStore
from services.lib.storage.minio_store import MinioObjectStore


def test_storage_key_is_deterministic():
    k1 = storage_key_for(
        prefix="matter-1",
        sha256="a" * 64,
        filename="Some File.pdf",
    )
    k2 = storage_key_for(
        prefix="matter-1",
        sha256="a" * 64,
        filename="Some File.pdf",
    )
    assert k1 == k2
    assert k1.startswith("matter-1/aa/aa/aaaaaaaaaaaa_")
    assert k1.endswith("Some_File.pdf")


def test_storage_key_sanitises_prefix_and_filename():
    k = storage_key_for(
        prefix="../evil",
        sha256="b" * 64,
        filename="name with spaces & punctuation!.txt",
    )
    assert ".." not in k
    assert " " not in k
    assert "!" not in k


@pytest.mark.asyncio
async def test_local_object_store_roundtrip(tmp_path):
    store = LocalObjectStore(root=tmp_path / "obj")

    await store.ensure_bucket("b1")
    obj = await store.put_object(
        bucket="b1",
        key="prefix/file.bin",
        data=b"hello world",
        content_type="application/octet-stream",
    )
    assert obj.uri == "s3://b1/prefix/file.bin"

    assert await store.exists("b1", "prefix/file.bin")
    got = await store.get_object("b1", "prefix/file.bin")
    assert got == b"hello world"

    url = await store.presign_get("b1", "prefix/file.bin")
    assert url.startswith("file://")


@pytest.mark.asyncio
async def test_ensure_default_buckets_bootstraps_public_and_private(monkeypatch):
    calls: list[str] = []

    class FakeStore:
        async def ensure_bucket(self, bucket: str) -> None:
            calls.append(bucket)

    from services.lib.storage import factory

    monkeypatch.setattr(factory, "get_object_store", lambda: FakeStore())
    monkeypatch.setattr(factory.settings, "minio_bucket_public", "pub")
    monkeypatch.setattr(factory.settings, "minio_bucket_private", "priv")

    await ensure_default_buckets()

    assert calls == ["pub", "priv"]


@pytest.mark.asyncio
async def test_minio_get_object_recovers_once_from_missing_bucket():
    store = object.__new__(MinioObjectStore)
    store._buckets_ensured = set()

    calls: list[tuple[str, str]] = []
    ensured: list[str] = []

    class NoSuchBucketError(Exception):
        code = "NoSuchBucket"

    def _sync_get(bucket: str, key: str) -> bytes:
        calls.append((bucket, key))
        if len(calls) == 1:
            raise NoSuchBucketError("bucket missing")
        return b"payload"

    def _sync_ensure_bucket(bucket: str) -> None:
        ensured.append(bucket)

    store._sync_get = _sync_get  # type: ignore[method-assign]
    store._sync_ensure_bucket = _sync_ensure_bucket  # type: ignore[method-assign]

    payload = await store.get_object("lexgraph-private", "m1/ab/cd/file.txt")

    assert payload == b"payload"
    assert ensured == ["lexgraph-private"]
    assert calls == [
        ("lexgraph-private", "m1/ab/cd/file.txt"),
        ("lexgraph-private", "m1/ab/cd/file.txt"),
    ]
