from __future__ import annotations

from services.runner import run

from .agent import EnrichAgent


def main() -> None:
    run(EnrichAgent())
