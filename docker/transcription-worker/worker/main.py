"""Boucle principale du worker de transcription.

Cycle (cf. spec 04 § Architecture du worker) :
    register_worker(idle) →  while not shutdown:
        claim_next_job → process_job → mark_done | handle_error
        update_worker_status(idle, last_activity_at)
    update_worker_status(stopped) + close pool

`process_job` télécharge l'audio MinIO, le passe au provider, upload le pivot,
et propage le statut au source_item. `handle_error` classifie l'exception et
trace dans `error_history`.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import structlog

from worker.config import Settings, settings
from worker.db import (
    claim_next_job,
    mark_job_done,
    mark_job_failed,
    register_worker,
    update_source_item_to_transcribed,
    update_worker_status,
)
from worker.error_classifier import classify_error
from worker.minio_client import download_audio, upload_transcript
from worker.providers.base import TranscriptionProvider

log = structlog.get_logger(__name__)


def build_provider(name: str, s: Settings) -> TranscriptionProvider:
    """Dispatch nom logique → instance provider."""
    if name == "openai-whisper":
        from worker.providers.openai_whisper import OpenAIWhisperProvider

        return OpenAIWhisperProvider(api_key=s.openai_api_key)
    if name == "faster-whisper":
        from worker.providers.faster_whisper import FasterWhisperProvider

        return FasterWhisperProvider(
            model_size=s.faster_whisper_model,
            device=s.faster_whisper_device,
            compute_type=s.faster_whisper_compute_type,
        )
    raise ValueError(f"Unknown provider: {name}")


def _build_transcript_s3_key(audio_s3_key: str) -> str:
    """Convention : corpus-audio/<path>.mp3 → corpus-transcripts/<path>.json."""
    base = audio_s3_key.replace("corpus-audio/", "corpus-transcripts/", 1)
    head, _, _ext = base.rpartition(".")
    return f"{head}.json" if head else f"{base}.json"


async def process_job(
    job: dict[str, Any],
    provider: TranscriptionProvider,
    pool: asyncpg.Pool,
    settings: Settings,
) -> None:
    """Traite un job claimé : download → transcribe → upload → mark_done."""
    audio_path = Path(tempfile.gettempdir()) / f"{job['id']}.audio"
    download_audio(job["audio_s3_key"], audio_path)
    try:
        pivot = await provider.transcribe(
            str(audio_path), language=job.get("language"),
        )
        cost = provider.estimate_cost(pivot.duration_s)
        pivot.metadata["cost_estimate_usd"] = cost

        transcript_key = _build_transcript_s3_key(job["audio_s3_key"])
        upload_transcript(transcript_key, pivot.to_dict())

        await mark_job_done(
            job["id"],
            provider_used=provider.name,
            cost_estimate_usd=cost,
            cost_actual_usd=None,
            result_s3_key=transcript_key,
            pool=pool,
        )
        await update_source_item_to_transcribed(
            job["source_item_id"], transcript_key, pool=pool,
        )
        # V2 : le pipeline s'arrête à `transcribed` → dépôt docflow (côté
        # backend). Le chunking/indexation pgvector (Sprint 4) est abandonné.
    finally:
        audio_path.unlink(missing_ok=True)


async def handle_error(
    job: dict[str, Any],
    provider: TranscriptionProvider,
    exc: BaseException,
    pool: asyncpg.Pool,
    settings: Settings,
) -> None:
    """Classifie l'exception, append à error_history et mark_job_failed.

    NB : la désactivation effective de la clé + la bascule des jobs sont
    pilotées côté backend (worker_manager) sur PG NOTIFY ou autre signal —
    ce worker se contente de tracer la catégorie pour que le backend agisse.
    """
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
        except Exception:  # noqa: BLE001  body non-JSON ou vide
            body = {}
        classified = classify_error(
            provider_name=provider.name,
            status_code=exc.response.status_code,
            body=body,
        )
        category = classified.category.value
        message = classified.message
        log.warning(
            "transcription_provider_http_error",
            job_id=str(job["id"]), category=category,
            should_disable_key=classified.should_disable_key,
            status_code=exc.response.status_code,
        )
        # Si la clé est épuisée et qu'on est sur un pool user, on enregistre
        # qu'une bascule serait souhaitable. La logique effective est côté
        # backend (Phase F3) ; ici on laisse une trace dans error_history.
        if classified.should_disable_key and job.get("worker_pool_id", "").startswith("user_"):
            log.info(
                "would_reassign_jobs_to_shared",
                worker_pool_id=job.get("worker_pool_id"),
            )
    else:
        category = "unknown" if isinstance(exc, RuntimeError) else "transient"
        message = str(exc) or exc.__class__.__name__
        log.exception("transcription_unexpected_error", job_id=str(job["id"]))

    entry = {
        "at": datetime.now(UTC).isoformat(),
        "category": category,
        "message": message,
        "provider": provider.name,
    }
    await mark_job_failed(
        job["id"], error=message, error_history_entry=entry, pool=pool,
    )


def _install_signal_handlers(shutdown: asyncio.Event) -> None:
    """Pose des handlers SIGTERM/SIGINT qui set un asyncio.Event."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except NotImplementedError:
            # Windows : add_signal_handler ne supporte que SIGINT,
            # SIGTERM raise. On retombe sur signal.signal.
            signal.signal(sig, lambda *_: shutdown.set())


async def _wait_or_shutdown(shutdown: asyncio.Event, delay_s: float) -> None:
    """Attend delay_s secondes ou jusqu'à shutdown set."""
    try:
        async with asyncio.timeout(delay_s):
            await shutdown.wait()
    except TimeoutError:
        return


async def main() -> None:
    """Point d'entrée du container : registre worker, poll, process, cleanup."""
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )
    log.info(
        "worker_starting",
        worker_id=settings.worker_id,
        worker_pool_id=settings.worker_pool_id,
        provider=settings.transcription_provider,
    )

    provider = build_provider(settings.transcription_provider, settings)
    pool = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=2,
    )
    if pool is None:
        raise RuntimeError("Failed to create asyncpg pool")

    await register_worker(
        settings.worker_id, settings.worker_pool_id, provider.name,
        status="idle", host=None, pool=pool,
    )

    shutdown = asyncio.Event()
    _install_signal_handlers(shutdown)

    try:
        while not shutdown.is_set():
            job = await claim_next_job(
                settings.worker_pool_id, settings.worker_id, pool=pool,
            )
            if job is None:
                await _wait_or_shutdown(shutdown, settings.poll_interval_s)
                continue

            await update_worker_status(settings.worker_id, "busy", pool=pool)
            try:
                await process_job(job, provider, pool, settings)
            except Exception as exc:  # noqa: BLE001  — orchestration
                await handle_error(job, provider, exc, pool, settings)
            finally:
                await update_worker_status(
                    settings.worker_id, "idle",
                    last_activity_at=datetime.now(UTC), pool=pool,
                )
    finally:
        await update_worker_status(
            settings.worker_id, "stopped",
            stopped_at=datetime.now(UTC), pool=pool,
        )
        await pool.close()
        log.info("worker_stopped", worker_id=settings.worker_id)


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(main())
