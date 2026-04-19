"""Nyaya Anumana adapter.

Nyaya Anumana is an Indian legal NLI / reasoning corpus (IIIT Delhi, released
under CC-BY-4.0) built on top of Indian court judgments. For ingestion
purposes we treat every entry as a judgment excerpt — the graph writer will
tag it with ``source_tier=2`` (SC) or ``source_tier=3`` (HC) based on the
seed's ``court`` attribute.

Cache-first + seed-driven, same as the other public adapters:

  1. Seeds at ``configs/adapters/nyaya_anumana_seeds.yml`` are discovered.
  2. Any bare files dropped into ``data/raw/nyaya_anumana/`` are also picked
     up (operator override).
  3. HTTP fetch is used only when a seed has a ``url`` and no cached file.
"""

from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

import yaml

from ...core import get_logger, settings
from ...data_models.metadata import DocumentKind, JudgmentMetadata
from ...data_models.provenance import File, RawDocument, SourceRef, sha256_bytes
from ..http_fetcher import HttpFetcher


log = get_logger("adapter.nyaya_anumana")


class NyayaAnumanaAdapter:
    name = "nyaya_anumana"
    source_tier = 2  # default; overridden per-seed when ``court`` signals HC
    attribution = (
        "Nyaya Anumana — Indian legal reasoning corpus (IIIT Delhi, CC-BY-4.0)"
    )

    def __init__(self) -> None:
        self._cache = Path(settings.data_dir) / "raw" / "nyaya_anumana"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._seeds_path = (
            Path(settings.configs_dir) / "adapters" / "nyaya_anumana_seeds.yml"
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
        court_filter = {(c.strip().lower()) for c in (courts or [])}

        # Track external_ids we've already yielded from the seed list so the
        # bare-files fallback below does not re-emit them. This matters when
        # scripts/fetch_hf_corpora.py has populated BOTH the seed YAML and the
        # cache dir with files whose stems match seed external_ids — without
        # this guard the ingest pipeline would write two SourceEpisodes for
        # the same underlying document.
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
            court=str(ref.attrs.get("court") or "Supreme Court of India"),
            jurisdiction="IN",
        )
        log.info("nyaya_anumana.fetch", external_id=ref.external_id, bytes=file.size)
        return RawDocument(
            source_ref=ref,
            file=file,
            kind="public",
            metadata=meta.model_dump(mode="json"),
        )


def _suffix_for_mime(mime: str) -> str:
    if mime == "application/pdf":
        return ".pdf"
    if mime.startswith("text/plain"):
        return ".txt"
    if mime.startswith("text/html"):
        return ".html"
    if mime.startswith("application/json"):
        return ".json"
    return ".bin"


def _mime_for(p: Path) -> str:
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".html": "text/html",
        ".json": "application/json",
    }.get(p.suffix.lower(), "application/octet-stream")
