from __future__ import annotations

from services.runner import run

from .agent import SegmentAgent


def main() -> None:
    run(SegmentAgent())
