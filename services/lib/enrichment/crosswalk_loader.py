"""Loader for old ↔ new law crosswalks declared in configs/crosswalks/*.yml."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from ..core import settings


@dataclass
class CrosswalkEntry:
    source_section: str
    target_section: str
    mapping_type: str            # one_to_one / one_to_many / many_to_one / partial / none
    topic: str | None = None
    notes: str | None = None


@dataclass
class Crosswalk:
    name: str
    version: str
    source_act: str
    target_act: str
    notes: str | None
    entries: list[CrosswalkEntry] = field(default_factory=list)

    def lookup_source(self, section: str) -> list[CrosswalkEntry]:
        return [e for e in self.entries if _norm(e.source_section) == _norm(section)]

    def lookup_target(self, section: str) -> list[CrosswalkEntry]:
        return [e for e in self.entries if _norm(e.target_section) == _norm(section)]


def _norm(s: str) -> str:
    return str(s).strip().lower().replace(" ", "")


_KEY_MAP = {
    "ipc_bns": ("ipc", "bns"),
    "crpc_bnss": ("crpc", "bnss"),
    "iea_bsa": ("iea", "bsa"),
}


def load_crosswalk(path: Path) -> Crosswalk:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    name = path.stem
    src_key, tgt_key = _KEY_MAP.get(name, ("source", "target"))
    entries = [
        CrosswalkEntry(
            source_section=str(row[src_key]),
            target_section=str(row[tgt_key]),
            mapping_type=str(row.get("mapping_type", "partial")),
            topic=row.get("topic"),
            notes=row.get("notes"),
        )
        for row in data.get("mappings", [])
    ]
    return Crosswalk(
        name=name,
        version=str(data.get("version", "0")),
        source_act=str(data.get("source_act", "")),
        target_act=str(data.get("target_act", "")),
        notes=data.get("notes"),
        entries=entries,
    )


def load_all_crosswalks() -> dict[str, Crosswalk]:
    root = settings.configs_dir / "crosswalks"
    return {p.stem: load_crosswalk(p) for p in sorted(root.glob("*.yml"))}
