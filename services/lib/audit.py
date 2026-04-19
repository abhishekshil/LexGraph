"""Append-only provenance audit log.

Every ingestion, segmentation, enrichment and graph-write emits a line to a
daily NDJSON file at ``<data_dir>/audit/<yyyy-mm-dd>.log``. This is a belt-and-
braces record independent of the graph — if the graph is ever rebuilt or
compromised we can still prove which events landed, when, and with what hash.

Keep this layer dependency-light: just JSON + a lock. It must never block the
event bus.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .core import get_logger, settings


log = get_logger("audit")


class ProvenanceAudit:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or (Path(settings.data_dir) / "audit")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _path_for(self, ts: datetime) -> Path:
        return self.root / f"{ts:%Y-%m-%d}.log"

    async def log(self, event_type: str, **fields: Any) -> None:
        ts = datetime.now(timezone.utc)
        record = {
            "ts": ts.isoformat(),
            "event_type": event_type,
            **{k: _json_safe(v) for k, v in fields.items() if v is not None},
        }
        path = self._path_for(ts)
        try:
            async with self._lock:
                await asyncio.to_thread(
                    _append_line, path, json.dumps(record, ensure_ascii=False)
                )
        except Exception as e:  # noqa: BLE001
            log.warning("audit.write_failed", error=str(e), event_type=event_type)


def _append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(line)
        f.write("\n")


def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v]
    if isinstance(v, dict):
        return {k: _json_safe(x) for k, x in v.items()}
    return str(v)


provenance_audit = ProvenanceAudit()
