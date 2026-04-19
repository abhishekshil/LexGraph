from __future__ import annotations

from services.runner import run

from .agent import GenerationAgent


def main() -> None:
    run(GenerationAgent())
