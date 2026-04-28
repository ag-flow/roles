"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.logging_setup import configure_logging
from role_builder.routes import (
    corpus,
    credentials,
    health,
    me,
    prompts,
    scraping_jobs,
    sources,
    synthesis,
    transcription_keys,
    websocket,
)
from role_builder.services.chunking_worker import ChunkingWorker
from role_builder.services.scraper_orchestrator import ScraperOrchestrator
from role_builder.services.worker_manager import WorkerManager
from role_builder.services.ws_relay import ws_relay

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle."""
    configure_logging(settings.log_level)
    if db_pool._pool is None:  # noqa: SLF001 — autorise injection en tests
        await db_pool.connect()

    stop = asyncio.Event()
    orchestrator_task: asyncio.Task[None] | None = None
    if not settings.disable_orchestrator:
        orchestrator = ScraperOrchestrator(pool=db_pool.pool)
        orchestrator_task = asyncio.create_task(
            orchestrator.run_loop(stop), name="scraper-orchestrator"
        )
        log.info("orchestrator.started")

    if not settings.disable_ws_relay:
        await ws_relay.start()

    worker_manager_task: asyncio.Task[None] | None = None
    if not settings.disable_worker_manager:
        worker_manager = WorkerManager(pool=db_pool.pool, image_tag=settings.worker_image_tag)
        worker_manager_task = asyncio.create_task(
            worker_manager.run_auto_stop_loop(
                stop, period_seconds=settings.worker_auto_stop_period_s
            ),
            name="worker-manager-auto-stop",
        )
        log.info("worker_manager.started")

    chunking_worker_task: asyncio.Task[None] | None = None
    if not settings.disable_chunking_worker:
        chunking_worker = ChunkingWorker(pool=db_pool.pool)
        chunking_worker_task = asyncio.create_task(
            chunking_worker.run_loop(stop),
            name="chunking-worker",
        )
        log.info("chunking_worker.started")

    try:
        yield
    finally:
        stop.set()
        if orchestrator_task is not None:
            try:
                await orchestrator_task
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("orchestrator.shutdown_error")
        if worker_manager_task is not None:
            try:
                await worker_manager_task
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("worker_manager.shutdown_error")
        if chunking_worker_task is not None:
            try:
                await chunking_worker_task
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("chunking_worker.shutdown_error")
        if not settings.disable_ws_relay:
            try:
                await ws_relay.stop()
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("ws_relay.shutdown_error")
        if db_pool._pool is not None:  # noqa: SLF001
            await db_pool.disconnect()


app = FastAPI(
    title="Role Builder API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # à restreindre en prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/health", tags=["health"])
app.include_router(me.router, prefix="/api", tags=["auth"])
app.include_router(sources.router, prefix="/api", tags=["sources"])
app.include_router(scraping_jobs.router, prefix="/api", tags=["scraping-jobs"])
app.include_router(corpus.router, prefix="/api", tags=["corpus"])
app.include_router(prompts.router, prefix="/api/prompts", tags=["prompts"])
app.include_router(synthesis.router, prefix="/api", tags=["synthesis"])
app.include_router(credentials.router, prefix="/api", tags=["credentials"])
app.include_router(transcription_keys.router, prefix="/api", tags=["transcription-keys"])
app.include_router(websocket.router, tags=["websocket"])
