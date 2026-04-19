"""IngestAgent: turns an ingest request into a RawDocument + SourceEpisode.

For private uploads the API writes bytes into the object store first and hands
the agent an ``s3://`` pointer plus the SHA. The agent verifies the hash on
read-back so any object-store tampering is caught before downstream work.

For public adapters the agent drives the adapter's ``discover()``/``fetch()``
and then persists the fetched bytes into the public bucket so the rest of the
pipeline reads from one place.
"""

from __future__ import annotations

from typing import Any

from services.lib.audit import provenance_audit
from services.lib.bus.factory import Streams
from services.lib.core import settings
from services.lib.data_models.events import (
    Event,
    IngestCompletedEvent,
    IngestRequestEvent,
)
from services.lib.data_models.provenance import (
    File,
    RawDocument,
    SourceEpisode,
    SourceRef,
    sha256_bytes,
)
from services.lib.graph import GraphWriter
from services.lib.ingestion import get_registry
from services.lib.storage import get_object_store, storage_key_for
from services.agent_base import Agent


class IngestAgent(Agent):
    name = "ingest"
    listens = (Streams.INGEST_REQUEST,)
    publishes = (Streams.INGEST_COMPLETED,)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.writer = GraphWriter()
        self.registry = get_registry()
        self.store = get_object_store()

    async def handle(self, event: Event) -> None:
        if not isinstance(event, IngestRequestEvent):
            return

        # An adapter run can discover many refs (e.g. every file cached in
        # data/raw/<adapter>/). We fan out here so a single "ingest public
        # ildc" trigger produces one SourceEpisode + downstream pipeline event
        # per discovered ref, instead of silently processing only the first.
        #
        # Failures are scoped per-ref: a remote seed that 403s (e.g.
        # indiacode.nic.in blocking our UA) must not prevent the locally
        # cached refs behind it from being processed. We log and keep going.
        if event.source == "adapter":
            adapter_name = event.adapter or ""
            adapter = self.registry.get(adapter_name)
            await self.writer.bootstrap()
            attribution = getattr(adapter, "attribution", None)
            ok = 0
            failed = 0
            async for ref in adapter.discover():
                try:
                    raw = await adapter.fetch(ref)
                    await self._persist_public(raw)
                    await self._emit_ingest_completed(event, raw, attribution)
                    ok += 1
                except Exception as e:
                    failed += 1
                    self.log.warning(
                        "ingest.ref_failed",
                        adapter=adapter_name,
                        external_id=ref.external_id,
                        url=ref.url,
                        error=str(e),
                    )
            if ok == 0 and failed == 0:
                self.log.warning("ingest.no_refs", adapter=adapter_name)
            else:
                self.log.info(
                    "ingest.adapter_run_done",
                    adapter=adapter_name,
                    refs=ok,
                    failed=failed,
                )
            return

        if event.source == "upload":
            raw, attribution = await self._handle_upload(event)
            if raw is None:
                return
            await self.writer.bootstrap()
            await self._emit_ingest_completed(event, raw, attribution)
            return

        self.log.warning("ingest.unknown_source", source=event.source)

    async def _emit_ingest_completed(
        self,
        event: IngestRequestEvent,
        raw: RawDocument,
        attribution: str | None,
    ) -> None:
        """Register a single RawDocument and fan an INGEST_COMPLETED event downstream."""
        await self.writer.register_file(raw.file.model_dump(mode="json"))
        episode = SourceEpisode.from_file(
            raw.file,
            kind=raw.kind,
            origin=event.adapter or event.source,
            matter_id=event.matter_id,
            attribution=attribution,
        )
        await self.writer.register_episode(episode)

        await provenance_audit.log(
            "ingest.completed",
            trace_id=event.trace_id,
            episode_id=episode.id,
            file_id=raw.file.id,
            storage_uri=raw.file.storage_uri,
            sha256=raw.file.sha256,
            bytes=raw.file.size,
            matter_id=event.matter_id,
            adapter=event.adapter,
            kind=raw.kind,
        )

        out = IngestCompletedEvent(
            trace_id=event.trace_id,
            tenant_id=event.tenant_id,
            matter_id=event.matter_id,
            raw_document=raw,
            episode=episode,
        )
        await self.bus.publish(Streams.INGEST_COMPLETED, out)
        self.log.info(
            "ingest.done",
            episode_id=episode.id,
            bytes=raw.file.size,
            source=event.source,
        )

    # -- private helpers ----------------------------------------------------

    async def _handle_upload(
        self, event: IngestRequestEvent
    ) -> tuple[RawDocument | None, str | None]:
        if not (event.upload_bucket and event.upload_key):
            self.log.warning("ingest.missing_upload_key", trace_id=event.trace_id)
            return None, None

        data = await self.store.get_object(event.upload_bucket, event.upload_key)
        computed_sha = sha256_bytes(data)
        if event.upload_sha256 and event.upload_sha256 != computed_sha:
            self.log.error(
                "ingest.sha_mismatch",
                expected=event.upload_sha256,
                actual=computed_sha,
                key=event.upload_key,
            )
            raise ValueError("upload sha256 mismatch")

        storage_uri = event.upload_uri or f"s3://{event.upload_bucket}/{event.upload_key}"
        file = File(
            storage_uri=storage_uri,
            mime=event.upload_mime or "application/octet-stream",
            sha256=computed_sha,
            size=event.upload_size or len(data),
            filename=event.upload_filename or event.upload_key.rsplit("/", 1)[-1],
        )
        raw = RawDocument(
            source_ref=SourceRef(
                adapter="upload",
                external_id=computed_sha[:16],
                url=storage_uri,
            ),
            file=file,
            kind="private" if event.matter_id else "public",
            metadata=(event.metadata.model_dump(mode="json") if event.metadata else {}),
            matter_id=event.matter_id,
        )
        return raw, None

    async def _persist_public(self, raw: RawDocument) -> None:
        """Copy a public-adapter fetch into the public bucket if not already there."""
        bucket = settings.minio_bucket_public
        key = storage_key_for(
            prefix=raw.source_ref.adapter,
            sha256=raw.file.sha256,
            filename=raw.file.filename,
        )
        if await self.store.exists(bucket, key):
            raw.file.storage_uri = f"s3://{bucket}/{key}"
            return

        # Read the bytes from wherever the adapter put them (typically local
        # cache) and upload.
        try:
            from pathlib import Path

            if raw.file.storage_uri.startswith("file://"):
                data = Path(raw.file.storage_uri.removeprefix("file://")).read_bytes()
            elif raw.file.storage_uri.startswith("s3://"):
                # already in object storage from the adapter
                return
            else:
                data = Path(raw.file.storage_uri).read_bytes()
        except Exception as e:
            self.log.warning("ingest.cannot_persist_public", error=str(e))
            return

        obj = await self.store.put_object(
            bucket=bucket,
            key=key,
            data=data,
            content_type=raw.file.mime,
            metadata={
                "adapter": raw.source_ref.adapter,
                "external_id": raw.source_ref.external_id,
                "sha256": raw.file.sha256,
            },
        )
        raw.file.storage_uri = obj.uri
