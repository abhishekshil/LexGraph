from __future__ import annotations

from services.runner import run

from .agent import IngestAgent


def main() -> None:
    run(IngestAgent())
