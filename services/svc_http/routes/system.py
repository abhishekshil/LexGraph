"""Operational discovery routes (service catalog)."""

from __future__ import annotations

from fastapi import APIRouter

from services.catalog import load_product_services

router = APIRouter(tags=["system"])


@router.get("/system/services")
async def list_product_services() -> dict:
    """Return the canonical product service map (IDs, modules, compose keys, streams)."""
    cat = load_product_services()
    return {
        "version": cat.version,
        "services": [s.model_dump() for s in cat.services],
    }
