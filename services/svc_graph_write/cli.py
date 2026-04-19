from __future__ import annotations

from services.runner import run

from .agent import GraphWriterAgent


def main() -> None:
    run(GraphWriterAgent())
