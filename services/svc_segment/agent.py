"""SegmentAgent: parse + legal-structure-aware segmentation.

Reads bytes from the object store (or local path for adapter-cached files),
parses per document kind, falls back to OCR when text density is low, then
produces SourceSpan records with document-aware structure labels.
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any

from services.lib.audit import provenance_audit
from services.lib.bus.factory import Streams
from services.lib.core import settings
from services.lib.data_models.events import (
    Event,
    IngestCompletedEvent,
    SegmentCompletedEvent,
)
from services.lib.data_models.metadata import DocumentKind
from services.lib.data_models.provenance import SourceSpan
from services.lib.graph import GraphWriter
from services.lib.normalization import segment_parsed_document
from services.lib.ocr import ocr_pdf
from services.lib.parsers import ParsedDocument, parse_bytes
from services.lib.parsers.parser import _tempfile_for
from services.lib.storage import get_object_store
from services.agent_base import Agent

MIN_TEXT_CHARS_BEFORE_OCR = 80


class SegmentAgent(Agent):
    name = "segment"
    listens = (Streams.INGEST_COMPLETED,)
    publishes = (Streams.SEGMENT_COMPLETED,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.writer = GraphWriter()
        self.store = get_object_store()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, IngestCompletedEvent):
            return

        file = event.raw_document.file
        try:
            data = await self._load_bytes(file.storage_uri)
        except Exception as e:
            self.log.error(
                "segment.load_failed",
                storage_uri=file.storage_uri,
                error=str(e),
            )
            return

        parsed = parse_bytes(data, mime=file.mime, filename=file.filename)

        if parsed.encrypted:
            self.log.warning(
                "segment.skipped_encrypted",
                episode_id=event.episode.id,
                filename=file.filename,
            )
            return

        if (
            file.mime == "application/pdf"
            and settings.ocr_enabled
            and len(parsed.text.strip()) < MIN_TEXT_CHARS_BEFORE_OCR
        ):
            parsed = await self._run_ocr(data, parsed)

        kind = _kind_from_metadata(event.raw_document.metadata)

        seg_result = segment_parsed_document(
            text=parsed.text,
            page_offsets=parsed.page_offsets,
            doc_kind=kind,
        )

        spans: list[SourceSpan] = []
        for seg in seg_result.segments:
            sp = SourceSpan(
                episode_id=event.episode.id,
                file_id=file.id,
                page=seg.page,
                char_start=seg.char_start,
                char_end=seg.char_end,
                text=seg.text,
                matter_id=event.matter_id,
                extra={
                    "seg_node_type": seg.node_type,
                    "seg_label": seg.label,
                    "seg_parent_label": seg.parent_label,
                    **seg.extra,
                },
            )
            spans.append(sp)
            await self.writer.register_span(sp)

        out = SegmentCompletedEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            episode_id=event.episode.id,
            spans=spans,
            hints={"doctype": kind.value, "used_ocr": parsed.used_ocr},
        )
        await self.bus.publish(Streams.SEGMENT_COMPLETED, out)
        await provenance_audit.log(
            "segment.completed",
            trace_id=event.trace_id,
            episode_id=event.episode.id,
            spans=len(spans),
            used_ocr=parsed.used_ocr,
            doctype=kind.value,
            matter_id=event.matter_id,
        )
        self.log.info(
            "segment.done",
            episode_id=event.episode.id,
            spans=len(spans),
            used_ocr=parsed.used_ocr,
            doctype=kind.value,
        )

    # -- helpers ------------------------------------------------------------

    async def _load_bytes(self, uri: str) -> bytes:
        if uri.startswith("s3://"):
            _, _, rest = uri.partition("s3://")
            bucket, _, key = rest.partition("/")
            return await self.store.get_object(bucket, key)
        if uri.startswith("file://"):
            return Path(uri.removeprefix("file://")).read_bytes()
        return Path(uri).read_bytes()

    async def _run_ocr(
        self,
        data: bytes,
        parsed: ParsedDocument,
    ) -> ParsedDocument:
        tmp = _tempfile_for(data, suffix=".pdf")
        try:
            ocr_res = ocr_pdf(tmp)
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        parsed.text = ocr_res.text
        parsed.page_offsets = ocr_res.page_offsets
        parsed.used_ocr = True
        return parsed


def _kind_from_metadata(metadata: dict[str, Any]) -> DocumentKind:
    raw = metadata.get("kind", DocumentKind.GENERIC.value)
    try:
        return DocumentKind(raw)
    except ValueError:
        return DocumentKind.GENERIC
