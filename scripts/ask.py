"""CLI shortcut: python -m scripts.ask "what are the ingredients of theft?" """

from __future__ import annotations

import asyncio
import json
import sys

from services.lib.core import configure_logging
from services.lib.generation import GroundedGenerator
from services.lib.retrieval import RetrievalOrchestrator


async def _go(q: str) -> None:
    configure_logging()
    orch = RetrievalOrchestrator()
    pack = await orch.answer(question=q)
    gen = GroundedGenerator()
    ans = await gen.generate(pack, trace_id="cli")
    print(json.dumps(ans.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What are the ingredients of theft under Section 378 IPC?"
    asyncio.run(_go(q))
