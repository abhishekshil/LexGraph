"""Shared async runner for agent microservices."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal

from services.agent_base import Agent
from services.lib.core import get_logger
from services.lib.storage import ensure_default_buckets


def run(agent: Agent) -> None:
    log = get_logger(f"worker.{agent.name}")

    async def _main() -> None:
        consumer = os.environ.get("WORKER_CONSUMER", f"{agent.name}-{os.getpid()}")
        log.info("worker.start", agent=agent.name, consumer=consumer)
        try:
            await ensure_default_buckets()
        except Exception as e:  # noqa: BLE001
            log.warning("worker.storage_bootstrap_failed", agent=agent.name, error=str(e))
        stop = asyncio.Event()

        def _sig(*_a: object) -> None:
            log.info("worker.sigterm", agent=agent.name)
            stop.set()

        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _sig)

        task = asyncio.create_task(agent.run_forever(consumer=consumer))
        await stop.wait()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(_main())
