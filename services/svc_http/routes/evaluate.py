from __future__ import annotations

from fastapi import APIRouter

from ...lib.evaluation.runner import EvaluationRunner


router = APIRouter(prefix="/evaluate", tags=["evaluate"])


@router.post("/{dataset}")
async def run_eval(dataset: str):
    runner = EvaluationRunner()
    return await runner.run(dataset)
