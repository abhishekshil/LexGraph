"""Runtime registry of public-source adapters, flag-driven."""

from __future__ import annotations

from functools import lru_cache

from ..core import settings, get_logger
from .base import PublicSourceAdapter


log = get_logger("ingestion.registry")


class AdapterRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, PublicSourceAdapter] = {}

    def register(self, adapter: PublicSourceAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> PublicSourceAdapter:
        if name not in self._adapters:
            raise KeyError(f"unknown adapter: {name}")
        return self._adapters[name]

    def names(self) -> list[str]:
        return sorted(self._adapters)


@lru_cache
def get_registry() -> AdapterRegistry:
    reg = AdapterRegistry()
    if settings.adapter_india_code:
        from .adapters.india_code import IndiaCodeAdapter
        reg.register(IndiaCodeAdapter())
    if settings.adapter_supreme_court_opendata:
        from .adapters.sci_opendata import SCIOpenDataAdapter
        reg.register(SCIOpenDataAdapter())
    if settings.adapter_high_court:
        from .adapters.hc_ecourts import HCeCourtsAdapter
        reg.register(HCeCourtsAdapter())
    if settings.adapter_nyaya_anumana:
        from .adapters.nyaya_anumana import NyayaAnumanaAdapter
        reg.register(NyayaAnumanaAdapter())
    if settings.adapter_ildc:
        from .adapters.ildc import ILDCAdapter
        reg.register(ILDCAdapter())
    if settings.adapter_opennyai:
        from .adapters.opennyai import OpenNyAIAdapter
        reg.register(OpenNyAIAdapter())
    log.info("ingestion.registry_ready", adapters=reg.names())
    return reg
