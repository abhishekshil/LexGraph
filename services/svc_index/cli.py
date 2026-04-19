from __future__ import annotations

from services.runner import run

from .agent import IndexAgent


def main() -> None:
    run(IndexAgent())
