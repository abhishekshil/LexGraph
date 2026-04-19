"""EvalAgent: runs the evaluation suite on request."""

from __future__ import annotations

from services.lib.bus.factory import Streams
from services.lib.data_models.events import Event
from services.lib.evaluation.runner import EvaluationRunner
from services.agent_base import Agent


class EvalAgent(Agent):
    name = "eval"
    listens = (Streams.EVAL_REQUEST,)
    publishes = (Streams.EVAL_REPORT,)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.runner = EvaluationRunner()

    async def handle(self, event: Event) -> None:
        dataset = event.model_dump().get("dataset") or "offence_ingredients_ipc_bns"
        report = await self.runner.run(dataset)
        self.log.info("eval.done", dataset=dataset, summary=report.get("summary"))
