"""FastAPI application entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from role_builder import __version__
from role_builder.config import settings
from role_builder.db import db_pool
from role_builder.logging_setup import configure_logging
from role_builder.mcp_server.server import mcp
from role_builder.migrations import run_migrations
from role_builder.routes import (
    apps,
    auth_local,
    credentials,
    health,
    me,
    scraping_jobs,
    sources,
    transcription_keys,
    websocket,
)
from role_builder.routes import (
    role_projects as role_projects_route,
)
from role_builder.routes import (
    version as version_route,
)
from role_builder.services import user_vault as user_vault_mod
from role_builder.services.deposit.factory import build_depositor
from role_builder.services.deposit.worker import DepositWorker
from role_builder.services.scheduler import RoleBuilderScheduler
from role_builder.services.scraper_orchestrator import ScraperOrchestrator
from role_builder.services.vault_resolver import VaultResolver
from role_builder.services.worker_manager import WorkerManager
from role_builder.services.ws_relay import ws_relay

log = structlog.get_logger(__name__)

# streamable_http_app() initialise mcp._session_manager (lazy) : appelé ici,
# avant que lifespan() ne le référence via mcp.session_manager.run().
mcp_asgi_app = mcp.streamable_http_app()


def _resolve_migrations_dir() -> Path:
    """Résout le dossier migrations selon le contexte de déploiement.

    - Image Docker (cf. backend/Dockerfile) : ``/app/migrations``
    - Dev local (depuis backend/) : ``../migrations`` relatif à la racine du repo
    - Override explicite : ``settings.migrations_dir`` (None par défaut)
    """
    if settings.migrations_dir is not None:
        return Path(settings.migrations_dir)
    docker_path = Path("/app/migrations")
    if docker_path.is_dir():
        return docker_path
    # Fallback dev : remonter depuis backend/src/role_builder/main.py
    return Path(__file__).resolve().parents[3] / "migrations"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown lifecycle.

    Englobe `mcp.session_manager.run()` : c'est le pattern documenté pour
    monter un serveur MCP streamable-http comme sous-application ASGI d'une
    app FastAPI existante (Starlette ne propage pas automatiquement le
    protocole lifespan aux sous-apps montées via `Mount`). `disable_mcp_server`
    saute ce bloc : `run()` est mono-usage par instance de session_manager
    (cf. commentaire Settings), incompatible avec les tests qui recréent un
    TestClient(app) par test contre le même singleton `mcp`.
    """
    if settings.disable_mcp_server:
        async with _lifespan_body(app):
            yield
        return
    async with mcp.session_manager.run():
        async with _lifespan_body(app):
            yield


@asynccontextmanager
async def _lifespan_body(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.log_level)
    if not settings.disable_vault:
        log.info("vault.resolver.starting")
        try:
            resolver = VaultResolver()
            await asyncio.to_thread(resolver.resolve_settings, settings)
            user_vault_mod.init_service(resolver.get_client())
            log.info("vault.resolver.done")
        except RuntimeError as exc:
            log.critical("vault.resolver.failed", error=str(exc))
            raise
    if db_pool._pool is None:  # noqa: SLF001 — autorise injection en tests
        await db_pool.connect()

    # Migrations DB — bloquant, exécuté avant que l'app commence à servir.
    # Si fail (extension manquante, fichier corrompu, lock contention), on
    # relève l'exception : le container redémarre en boucle, ce qui est
    # voulu pour visibilité immédiate du problème.
    if not settings.disable_migrations:
        applied = await run_migrations(
            _resolve_migrations_dir(), pool=db_pool.pool,
        )
        log.info("migrations.lifespan.applied", count=len(applied))

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

    deposit_worker_task: asyncio.Task[None] | None = None
    if not settings.disable_deposit_worker:
        deposit_worker = DepositWorker(
            pool=db_pool.pool,
            depositor=build_depositor(settings),
            max_attempts=settings.deposit_max_attempts,
            backoff_base_s=settings.deposit_backoff_base_s,
            poll_interval_s=settings.deposit_poll_interval_s,
        )
        deposit_worker_task = asyncio.create_task(
            deposit_worker.run_loop(stop), name="deposit-worker"
        )
        log.info("deposit_worker.started", backend=settings.deposit_backend)

    scheduler: RoleBuilderScheduler | None = None
    if not settings.disable_scheduler:
        scheduler = RoleBuilderScheduler(pool=db_pool.pool)
        scheduler.start()

    try:
        yield
    finally:
        stop.set()
        if scheduler is not None:
            try:
                await scheduler.shutdown()
            except Exception:  # noqa: BLE001
                log.exception("scheduler.shutdown_error")
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
        if deposit_worker_task is not None:
            try:
                await deposit_worker_task
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("deposit_worker.shutdown_error")
        if not settings.disable_ws_relay:
            try:
                await ws_relay.stop()
            except Exception:  # noqa: BLE001 — shutdown best-effort
                log.exception("ws_relay.shutdown_error")
        if db_pool._pool is not None:  # noqa: SLF001
            await db_pool.disconnect()


app = FastAPI(
    title="Role Builder API",
    version=__version__,
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
app.include_router(credentials.router, prefix="/api", tags=["credentials"])
app.include_router(transcription_keys.router, prefix="/api", tags=["transcription-keys"])
app.include_router(role_projects_route.router, prefix="/api", tags=["role-projects"])
app.include_router(version_route.router, prefix="/api", tags=["version"])
app.include_router(apps.router, prefix="/api", tags=["apps"])
app.include_router(auth_local.router, prefix="/api", tags=["auth-local"])
app.include_router(websocket.router, tags=["websocket"])

# Façade MCP roles__* (backend), exposée à la passerelle sur /mcp.
app.mount("/mcp", mcp_asgi_app)
