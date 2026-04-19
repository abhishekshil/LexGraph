"""India Code adapter — https://www.indiacode.nic.in.

The adapter is seed-driven (YAML at ``configs/adapters/india_code_seeds.yml``)
and cache-first. For every seed:

  1. If the PDF already exists under ``data/raw/india_code/<external_id>.pdf``,
     use it (offline-safe).
  2. Otherwise fetch via the shared :class:`HttpFetcher` (polite rate-limit +
     robots check) and persist to the local cache.

This deliberately does not implement a general crawler — indiacode.nic.in's
browse endpoints are unstable — but all downstream plumbing is wired so adding
new seeds or a different crawler is a one-file change.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml

from ...core import get_logger, settings
from ...data_models.metadata import DocumentKind, StatuteMetadata
from ...data_models.provenance import File, RawDocument, SourceRef, sha256_bytes
from ..http_fetcher import HttpFetcher


log = get_logger("adapter.india_code")


class IndiaCodeAdapter:
    name = "india_code"
    source_tier = 1
    attribution = "India Code, Govt. of India — https://www.indiacode.nic.in"

    def __init__(self) -> None:
        self._cache = Path(settings.data_dir) / "raw" / "india_code"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._seeds_path = Path(settings.configs_dir) / "adapters" / "india_code_seeds.yml"
        self._http = HttpFetcher.shared()

    def _load_seeds(self) -> list[dict]:
        if not self._seeds_path.exists():
            return []
        with self._seeds_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return list(data.get("seeds") or [])

    async def discover(self, **filters: object) -> AsyncIterator[SourceRef]:
        # 1) seeds from the YAML index
        for seed in self._load_seeds():
            yield SourceRef(
                adapter=self.name,
                external_id=seed["external_id"],
                url=seed.get("url") or "",
                attrs={
                    "title": seed.get("title", ""),
                    "act_name": seed.get("act_name", ""),
                    "mime": seed.get("mime", "application/pdf"),
                    "from_seeds": "1",
                },
            )
        # 2) any bare files dropped into the cache dir (operator override)
        for p in sorted(self._cache.glob("*")):
            if not p.is_file() or p.suffix.lower() in {".tmp", ".part"}:
                continue
            yield SourceRef(
                adapter=self.name,
                external_id=p.stem,
                url=f"file://{p}",
                attrs={"mime": _mime_for(p)},
            )

    async def fetch(self, ref: SourceRef) -> RawDocument:
        cache_path, data, mime = await self._resolve_bytes(ref)

        sha = sha256_bytes(data)
        file = File(
            storage_uri=str(cache_path),
            mime=mime,
            sha256=sha,
            size=len(data),
            filename=cache_path.name,
        )
        meta = StatuteMetadata(
            title=str(ref.attrs.get("title") or ref.external_id.replace("_", " ")),
            filename=cache_path.name,
            source_id=ref.external_id,
            kind=DocumentKind.STATUTE,
            jurisdiction="IN",
            act_name=str(ref.attrs.get("act_name") or ref.external_id.replace("_", " ")),
        )
        log.info("india_code.fetch", external_id=ref.external_id, bytes=file.size)
        return RawDocument(
            source_ref=ref,
            file=file,
            kind="public",
            metadata=meta.model_dump(mode="json"),
        )

    async def _resolve_bytes(
        self, ref: SourceRef
    ) -> tuple[Path, bytes, str]:
        """Return ``(local_path, bytes, mime)``, fetching over HTTP if needed."""
        mime = str(ref.attrs.get("mime") or "application/pdf")
        suffix = _suffix_for_mime(mime)
        local = self._cache / f"{ref.external_id}{suffix}"

        if ref.url.startswith("file://"):
            # Honour the real on-disk path so storage_uri stays pointable.
            # Without this the downstream segment worker would receive e.g.
            # "foo.bin" because mime=text/plain mapped to the generic suffix.
            real = Path(ref.url.removeprefix("file://"))
            data = real.read_bytes()
            return real, data, mime

        if local.exists():
            return local, local.read_bytes(), mime

        if not ref.url:
            raise FileNotFoundError(f"no url / cache for {ref.external_id}")

        data, headers = await self._http.get_bytes(ref.url)
        if "content-type" in headers and "pdf" in headers["content-type"]:
            mime = "application/pdf"
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(data)
        return local, data, mime


def _suffix_for_mime(mime: str) -> str:
    if mime == "application/pdf":
        return ".pdf"
    if mime.startswith("text/html"):
        return ".html"
    if mime.startswith("text/plain"):
        return ".txt"
    if mime.startswith("application/xml") or mime == "text/xml":
        return ".xml"
    return ".bin"


def _mime_for(p: Path) -> str:
    sfx = p.suffix.lower()
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".html": "text/html",
        ".htm": "text/html",
        ".xml": "application/xml",
    }.get(sfx, "application/octet-stream")
