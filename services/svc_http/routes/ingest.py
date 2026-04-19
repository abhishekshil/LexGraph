from __future__ import annotations

import mimetypes
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ...lib.bus import get_bus
from ...lib.bus.factory import Streams
from ...lib.core import get_logger, settings
from ...lib.data_models.events import IngestRequestEvent
from ...lib.data_models.metadata import DocumentKind, DocumentMetadata
from ...lib.data_models.provenance import sha256_bytes
from ...lib.storage import get_object_store, storage_key_for


log = get_logger("api.ingest")
router = APIRouter(prefix="/ingest", tags=["ingest"])


MAX_FILE_BYTES_DEFAULT = 200 * 1024 * 1024


@router.post("/public")
async def ingest_public(adapter: str = Form(...)):
    """Queue a public-source adapter run. The adapter picks up its own refs."""
    bus = get_bus()
    trace_id = f"trace_{uuid4().hex}"
    evt = IngestRequestEvent(trace_id=trace_id, source="adapter", adapter=adapter)
    await bus.publish(Streams.INGEST_REQUEST, evt)
    log.info("ingest.public.queued", adapter=adapter, trace_id=trace_id)
    return {"trace_id": trace_id, "queued": True, "adapter": adapter}


@router.post("/private")
async def ingest_private(
    file: UploadFile = File(...),
    matter_id: str = Form(...),
    kind: str = Form(DocumentKind.GENERIC.value),
):
    """Upload a private document.

    The file is streamed into the object store under the matter-scoped key
    ``<matter_id>/<sha>/<filename>``. Only an ``IngestRequestEvent`` with the
    object-store pointer is published; the raw bytes never sit on the API
    container's disk longer than the request lifetime.
    """
    try:
        doc_kind = DocumentKind(kind)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid kind: {kind}")

    max_bytes = (settings.ingest_max_file_mb or 200) * 1024 * 1024
    max_bytes = min(max_bytes, MAX_FILE_BYTES_DEFAULT)

    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    if len(data) > max_bytes:
        raise HTTPException(status_code=413, detail="file too large")

    sha = sha256_bytes(data)
    filename = file.filename or f"{sha[:12]}.bin"
    mime = (
        file.content_type
        or mimetypes.guess_type(filename)[0]
        or "application/octet-stream"
    )

    store = get_object_store()
    bucket = settings.minio_bucket_private
    key = storage_key_for(prefix=matter_id, sha256=sha, filename=filename)
    obj = await store.put_object(
        bucket=bucket,
        key=key,
        data=data,
        content_type=mime,
        metadata={"matter_id": matter_id, "kind": doc_kind.value, "sha256": sha},
    )

    meta = DocumentMetadata(
        filename=filename,
        matter_id=matter_id,
        kind=doc_kind,
        confidentiality="private",
    )
    trace_id = f"trace_{uuid4().hex}"
    evt = IngestRequestEvent(
        trace_id=trace_id,
        matter_id=matter_id,
        source="upload",
        upload_uri=obj.uri,
        upload_bucket=obj.bucket,
        upload_key=obj.key,
        upload_filename=filename,
        upload_mime=mime,
        upload_sha256=sha,
        upload_size=len(data),
        metadata=meta,
    )
    await get_bus().publish(Streams.INGEST_REQUEST, evt)

    log.info(
        "ingest.private.queued",
        trace_id=trace_id,
        matter_id=matter_id,
        bucket=bucket,
        key=key,
        sha=sha,
        size=len(data),
    )
    return {
        "trace_id": trace_id,
        "queued": True,
        "matter_id": matter_id,
        "kind": doc_kind.value,
        "storage_uri": obj.uri,
        "sha256": sha,
        "size": len(data),
    }
