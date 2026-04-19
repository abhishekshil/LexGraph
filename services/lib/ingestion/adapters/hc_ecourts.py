"""High Court judgments adapter (eCourts).

Cache-first + seed-driven. CAPTCHA-guarded endpoints are intentionally not
automated; operators drop judgment PDFs into ``data/raw/hc_ecourts/`` or seed
direct PDF URLs in ``configs/adapters/hc_ecourts_seeds.yml``.

Attribution text includes the originating court when provided in the seed.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml

from ...core import get_logger, settings
from ...data_models.metadata import DocumentKind, JudgmentMetadata
from ...data_models.provenance import File, RawDocument, SourceRef, sha256_bytes
from ..http_fetcher import HttpFetcher


log = get_logger("adapter.hc_ecourts")


class HCeCourtsAdapter:
    name = "hc_ecourts"
    source_tier = 3
    attribution = "High Court judgment via eCourts public portal (Govt. of India)"

    def __init__(self) -> None:
        self._cache = Path(settings.data_dir) / "raw" / "hc_ecourts"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._seeds_path = (
            Path(settings.configs_dir) / "adapters" / "hc_ecourts_seeds.yml"
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
        courts: list[str] | None = None,
        **_filters: object,
    ) -> AsyncIterator[SourceRef]:
        court_filter = set((c.strip().lower() for c in (courts or [])))

        for seed in self._load_seeds():
            court = str(seed.get("court", ""))
            if court_filter and court.lower() not in court_filter:
                continue
            yield SourceRef(
                adapter=self.name,
                external_id=seed["external_id"],
                url=seed.get("url") or "",
                attrs={
                    "title": seed.get("title", ""),
                    "court": court,
                    "year": str(seed.get("year", "")),
                    "mime": seed.get("mime", "application/pdf"),
                },
            )

        for p in sorted(self._cache.glob("*.pdf")):
            yield SourceRef(
                adapter=self.name,
                external_id=p.stem,
                url=f"file://{p}",
                attrs={"mime": "application/pdf"},
            )

    async def fetch(self, ref: SourceRef) -> RawDocument:
        mime = str(ref.attrs.get("mime") or "application/pdf")
        suffix = ".pdf" if "pdf" in mime else ".bin"
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
            court=str(ref.attrs.get("court") or "High Court"),
            jurisdiction="IN",
        )
        log.info("hc_ecourts.fetch", external_id=ref.external_id, bytes=file.size)
        return RawDocument(
            source_ref=ref,
            file=file,
            kind="public",
            metadata=meta.model_dump(mode="json"),
        )
