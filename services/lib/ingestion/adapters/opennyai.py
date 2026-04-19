"""OpenNyAI adapter.

OpenNyAI (https://opennyai.org) is an initiative (Agami, EkStep, Thoughtworks)
publishing open datasets and models for Indian law — rhetorical-role-tagged
judgments, NER, legal summarisation corpora etc. Datasets are released under
CC-BY-4.0 / Apache-2.0 via https://github.com/OpenNyAI.

Cache-first + seed-driven, matching the other adapters:

  1. Seeds at ``configs/adapters/opennyai_seeds.yml``.
  2. Bare files under ``data/raw/opennyai/`` are also picked up.
  3. HTTP fetch is only attempted when a seed URL is present.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml

from ...core import get_logger, settings
from ...data_models.metadata import DocumentKind, JudgmentMetadata
from ...data_models.provenance import File, RawDocument, SourceRef, sha256_bytes
from ..http_fetcher import HttpFetcher


log = get_logger("adapter.opennyai")


class OpenNyAIAdapter:
    name = "opennyai"
    source_tier = 3  # mixed: SC + HC + tribunals; conservative default
    attribution = (
        "OpenNyAI open-source Indian legal datasets — "
        "https://opennyai.org (CC-BY-4.0 / Apache-2.0)"
    )

    def __init__(self) -> None:
        self._cache = Path(settings.data_dir) / "raw" / "opennyai"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._seeds_path = Path(settings.configs_dir) / "adapters" / "opennyai_seeds.yml"
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
        court_filter = {(c.strip().lower()) for c in (courts or [])}

        # See nyaya_anumana.discover for the rationale: dedupe seed vs. bare
        # file so fetch_hf_corpora writing both does not cause double-ingest.
        seen: set[str] = set()
        for seed in self._load_seeds():
            court = str(seed.get("court", ""))
            if court_filter and court.lower() not in court_filter:
                continue
            ext_id = seed["external_id"]
            seen.add(ext_id)
            yield SourceRef(
                adapter=self.name,
                external_id=ext_id,
                url=seed.get("url") or "",
                attrs={
                    "title": seed.get("title", ""),
                    "court": court,
                    "year": str(seed.get("year", "")),
                    "mime": seed.get("mime", "text/plain"),
                    "dataset": seed.get("dataset", ""),
                },
            )

        for p in sorted(self._cache.glob("*")):
            if not p.is_file() or p.stem in seen:
                continue
            yield SourceRef(
                adapter=self.name,
                external_id=p.stem,
                url=f"file://{p}",
                attrs={"mime": _mime_for(p)},
            )

    async def fetch(self, ref: SourceRef) -> RawDocument:
        mime = str(ref.attrs.get("mime") or "text/plain")
        suffix = _suffix_for_mime(mime)
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
            court=str(ref.attrs.get("court") or "Indian Court"),
            jurisdiction="IN",
        )
        log.info("opennyai.fetch", external_id=ref.external_id, bytes=file.size)
        return RawDocument(
            source_ref=ref,
            file=file,
            kind="public",
            metadata=meta.model_dump(mode="json"),
        )


def _suffix_for_mime(mime: str) -> str:
    if mime == "application/pdf":
        return ".pdf"
    if mime.startswith("application/json"):
        return ".json"
    if mime.startswith("text/plain"):
        return ".txt"
    if mime.startswith("text/html"):
        return ".html"
    return ".bin"


def _mime_for(p: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".html": "text/html",
        ".json": "application/json",
    }.get(p.suffix.lower(), "application/octet-stream")
