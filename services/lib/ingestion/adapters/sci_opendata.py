"""Supreme Court of India open-data adapter.

Targets the CC-BY-4.0 dataset published at
https://github.com/vanga/indian-supreme-court-judgments and mirror URLs.

Like the India Code adapter, this is seed-driven + cache-first. Operators add
judgment URLs to ``configs/adapters/sci_opendata_seeds.yml`` or simply drop PDFs
into ``data/raw/sci_opendata/``.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml

from ...core import get_logger, settings
from ...data_models.metadata import DocumentKind, JudgmentMetadata
from ...data_models.provenance import File, RawDocument, SourceRef, sha256_bytes
from ..http_fetcher import HttpFetcher


log = get_logger("adapter.sci_opendata")


class SCIOpenDataAdapter:
    name = "sci_opendata"
    source_tier = 2
    attribution = (
        "Indian Supreme Court Judgments open dataset (CC-BY-4.0) — "
        "https://github.com/vanga/indian-supreme-court-judgments"
    )

    def __init__(self) -> None:
        self._cache = Path(settings.data_dir) / "raw" / "sci_opendata"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._seeds_path = (
            Path(settings.configs_dir) / "adapters" / "sci_opendata_seeds.yml"
        )
        self._http = HttpFetcher.shared()

    def _load_seeds(self) -> list[dict]:
        if not self._seeds_path.exists():
            return []
        with self._seeds_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return list(data.get("seeds") or [])

    async def discover(
        self,
        *,
        years: list[int] | None = None,
        **_filters: object,
    ) -> AsyncIterator[SourceRef]:
        year_filter = set(years or [])

        for seed in self._load_seeds():
            year = _year_from_name(seed.get("external_id", "")) or seed.get("year")
            if year_filter and year not in year_filter:
                continue
            yield SourceRef(
                adapter=self.name,
                external_id=seed["external_id"],
                url=seed.get("url") or "",
                attrs={
                    "title": seed.get("title", ""),
                    "court": seed.get("court") or "Supreme Court of India",
                    "year": str(year or ""),
                    "mime": seed.get("mime", "application/pdf"),
                },
            )

        for p in sorted(self._cache.glob("*")):
            if not p.is_file():
                continue
            year = _year_from_name(p.stem)
            if year_filter and year not in year_filter:
                continue
            yield SourceRef(
                adapter=self.name,
                external_id=p.stem,
                url=f"file://{p}",
                attrs={"year": str(year or ""), "mime": _mime_for(p)},
            )

    async def fetch(self, ref: SourceRef) -> RawDocument:
        mime = str(ref.attrs.get("mime") or "application/pdf")
        suffix = ".pdf" if "pdf" in mime else ".txt"
        local = self._cache / f"{ref.external_id}{suffix}"

        if ref.url.startswith("file://"):
            data = Path(ref.url.removeprefix("file://")).read_bytes()
        elif local.exists():
            data = local.read_bytes()
        elif ref.url:
            data, headers = await self._http.get_bytes(ref.url)
            if "content-type" in headers and "pdf" in headers["content-type"]:
                mime = "application/pdf"
            local.write_bytes(data)
        else:
            raise FileNotFoundError(f"no url / cache for {ref.external_id}")

        sha = sha256_bytes(data)
        file = File(
            storage_uri=str(local),
            mime=mime,
            sha256=sha,
            size=len(data),
            filename=local.name,
        )
        meta = JudgmentMetadata(
            title=str(ref.attrs.get("title") or ref.external_id.replace("_", " ")),
            filename=local.name,
            source_id=ref.external_id,
            kind=DocumentKind.JUDGMENT,
            court=str(ref.attrs.get("court") or "Supreme Court of India"),
            jurisdiction="IN",
        )
        log.info("sci_opendata.fetch", external_id=ref.external_id, bytes=file.size)
        return RawDocument(
            source_ref=ref,
            file=file,
            kind="public",
            metadata=meta.model_dump(mode="json"),
        )


def _year_from_name(name: str) -> int | None:
    for token in name.replace(".", "_").split("_"):
        if token.isdigit() and len(token) == 4:
            y = int(token)
            if 1900 <= y <= 2100:
                return y
    return None


def _mime_for(p: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".html": "text/html",
    }.get(p.suffix.lower(), "application/octet-stream")
