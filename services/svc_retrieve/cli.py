from __future__ import annotations

from services.runner import run

from .agent import RetrievalAgent


def main() -> None:
    run(RetrievalAgent())
