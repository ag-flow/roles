"""Orchestrator scrapers Sprint 2.

Pull les `scraping_jobs` pending en FIFO (FOR UPDATE SKIP LOCKED), lance
le container scraper correspondant via `docker_runner.run_container`, et
dispatche les events NDJSON vers `event_handlers.handle_scraper_event`.
Marque le job done|failed selon le returncode.

Cap simultané : `settings.max_concurrent_scrapers` via `asyncio.Semaphore`.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.db_helpers import scraping_jobs as sj
from role_builder.db_helpers import sources as sm
from role_builder.db_helpers.credentials import get_cookies_b64
from role_builder.services.docker_runner import run_container
from role_builder.services.event_handlers import handle_scraper_event

log = structlog.get_logger(__name__)

# Defaults applied to the stdin payload when not overridden at the job level.
_DEFAULT_OPTIONS = {
    "audio_format": "mp3",
    "audio_quality": 9,
    "audio_args": "-ac 1 -ar 16000 -b:a 32k",
    "sleep_interval_min": 3,
    "sleep_interval_max": 10,
}


class ScraperOrchestrator:
    """One instance per backend process. Use `run_loop` for the long-lived task."""

    def __init__(self, *, pool: asyncpg.Pool, worker_id: str = "orchestrator-1") -> None:
        self._pool = pool
        self._worker_id = worker_id
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_scrapers)

    async def process_one_job(self, job: dict[str, Any]) -> None:
        """Run a single scraping job: build payload, stream events, mark lifecycle."""
        job_id = job["id"]
        source_id = job["source_id"]

        await sj.mark_job_processing(job_id, pool=self._pool)

        source = await sm.get_source(source_id, pool=self._pool)
        if source is None:
            err = f"source {source_id} not found"
            log.error("orchestrator.source_missing", job_id=str(job_id), source_id=str(source_id))
            await sj.mark_job_failed(job_id, err, pool=self._pool)
            return

        platform = source["platform"]
        env = self._build_env(platform)
        payload = self._build_payload(job, source)
        image = f"agflow-scraper-{platform}:{settings.scraper_image_tag}"

        log.info(
            "orchestrator.process_start",
            job_id=str(job_id),
            platform=platform,
            command=job["command"],
            image=image,
        )

        returncode: int | None = None
        try:
            async for event in run_container(image, env, payload):
                if event.get("type") == "_exit":
                    returncode = int(event.get("returncode", -1))
                    continue
                await handle_scraper_event(event, job, pool=self._pool)
        except Exception as exc:  # noqa: BLE001 — orchestrator must keep running
            log.exception("orchestrator.process_error", job_id=str(job_id))
            await sj.mark_job_failed(job_id, f"orchestrator error: {exc}", pool=self._pool)
            return

        if returncode == 0:
            await sj.mark_job_done(job_id, pool=self._pool)
        else:
            await sj.mark_job_failed(
                job_id, f"scraper exited with returncode {returncode}", pool=self._pool
            )

    async def run_loop(self, stop_event: asyncio.Event) -> None:
        """Long-lived worker loop. Pulls pending jobs and dispatches them."""
        log.info("orchestrator.loop_start", worker_id=self._worker_id)
        while not stop_event.is_set():
            job = await sj.claim_next_pending_job(self._worker_id, pool=self._pool)
            if job is None:
                # Nothing to do; sleep until stop_event or 2s elapse.
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=2.0)
                except TimeoutError:
                    continue
                else:
                    break
            else:
                async with self._semaphore:
                    await self.process_one_job(job)
        log.info("orchestrator.loop_stop", worker_id=self._worker_id)

    # --- internals -------------------------------------------------------

    def _build_env(self, platform: str) -> dict[str, str]:
        env: dict[str, str] = {
            "MINIO_ENDPOINT": settings.minio_endpoint,
            "MINIO_ACCESS_KEY": settings.minio_access_key,
            "MINIO_SECRET_KEY": settings.minio_secret_key,
            "LOG_LEVEL": settings.log_level,
        }
        cookies = get_cookies_b64(platform)
        if cookies:
            env[f"{platform.upper()}_COOKIES_B64"] = cookies
        return env

    def _build_payload(self, job: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        prefix = f"{job['tenant_id']}/{source['role_project_id']}/{source['id']}/"
        return {
            "task_id": str(job["id"]),
            "command": job["command"],
            "url": source["url"],
            "options": dict(_DEFAULT_OPTIONS),
            "output": {
                "type": "minio",
                "endpoint": settings.minio_endpoint,
                "bucket": "corpus-audio",
                "prefix": prefix,
                "access_key": settings.minio_access_key,
                "secret_key": settings.minio_secret_key,
            },
        }
