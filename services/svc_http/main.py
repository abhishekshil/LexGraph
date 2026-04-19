"""FastAPI gateway."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..lib.core import get_logger, settings
from ..lib.graph import GraphWriter
from ..lib.storage import ensure_default_buckets
from .routes import evaluate, evidence, graph, ingest, query, system

log = get_logger("api")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    writer = GraphWriter()
    try:
        await writer.bootstrap()
    except Exception as e:
        log.warning("graph.bootstrap_failed", error=str(e))
    try:
        await ensure_default_buckets()
    except Exception as e:
        log.warning("storage.bootstrap_failed", error=str(e))
    log.info("api.ready", prefix=settings.api_prefix)
    yield


app = FastAPI(
    title="LexGraph API",
    version="0.1.0",
    description="Graph-first, citation-first Indian legal research.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix=settings.api_prefix)
app.include_router(query.router, prefix=settings.api_prefix)
app.include_router(evidence.router, prefix=settings.api_prefix)
app.include_router(graph.router, prefix=settings.api_prefix)
app.include_router(evaluate.router, prefix=settings.api_prefix)
app.include_router(system.router, prefix=settings.api_prefix)


@app.get("/")
async def root():
    return {"service": "lexgraph", "version": "0.1.0"}


def run() -> None:  # used by pyproject script entry
    import uvicorn
    uvicorn.run(
        "services.svc_http.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
