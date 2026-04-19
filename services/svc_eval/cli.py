from __future__ import annotations

from services.runner import run

from .agent import EvalAgent


def main() -> None:
    run(EvalAgent())
