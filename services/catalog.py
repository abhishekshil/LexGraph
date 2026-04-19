"""Load the canonical product service map from ``configs/product_services.yml``."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from services.lib.core.config import REPO_ROOT


class ProductService(BaseModel):
    """One deployable or routable unit (HTTP gateway or bus worker)."""

    id: str
    title: str
    kind: Literal["http", "worker"]
    python_module: str
    compose_service: str
    description: str = ""
    public_base_path: str | None = None
    listens: list[str] = Field(default_factory=list)
    publishes: list[str] = Field(default_factory=list)


class ProductServiceCatalog(BaseModel):
    version: int
    services: list[ProductService]


@lru_cache
def load_product_services() -> ProductServiceCatalog:
    path = REPO_ROOT / "configs" / "product_services.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ProductServiceCatalog.model_validate(raw)


def get_service(service_id: str) -> ProductService | None:
    cat = load_product_services()
    for s in cat.services:
        if s.id == service_id:
            return s
    return None
