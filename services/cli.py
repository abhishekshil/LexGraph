"""Operator CLI. `lexgraph --help` for commands."""

from __future__ import annotations

import asyncio
import json

import typer

from services.lib.core import configure_logging, settings
from services.lib.generation import GroundedGenerator
from services.lib.retrieval import RetrievalOrchestrator


app = typer.Typer(add_completion=False, help="LexGraph CLI")


@app.command()
def version() -> None:
    typer.echo("lexgraph 0.1.0")


@app.command()
def ask(question: str, matter: str | None = None, mode: str | None = None) -> None:
    configure_logging()

    async def _go() -> None:
        orch = RetrievalOrchestrator()
        pack = await orch.answer(
            question=question, matter_scope=matter, mode=mode or settings.retrieval_mode
        )
        gen = GroundedGenerator()
        answer = await gen.generate(pack, trace_id="cli")
        typer.echo(json.dumps(answer.model_dump(mode="json"), indent=2))

    asyncio.run(_go())


@app.command()
def eval_dataset(dataset: str) -> None:
    configure_logging()
    from services.lib.evaluation import EvaluationRunner

    async def _go() -> None:
        report = await EvaluationRunner().run(dataset)
        typer.echo(json.dumps(report.get("summary", {}), indent=2))

    asyncio.run(_go())


if __name__ == "__main__":
    app()
