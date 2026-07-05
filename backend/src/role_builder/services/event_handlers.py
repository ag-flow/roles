"""Dispatch des events NDJSON émis par les containers scrapers vers la DB.

Le scraper émet les types d'events documentés en spec 03 (started,
discovered, progress, item_done, item_failed, complete, error). Les
events internes injectés par docker_runner (`_invalid_line`, `_exit`)
sont logués mais ne déclenchent pas d'écriture DB — l'orchestrator
inspecte le returncode pour clore le job.
"""

from __future__ import annotations

from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import role_projects as rp
from role_builder.db_helpers import source_items as si
from role_builder.db_helpers import sources as sm
from role_builder.db_helpers import transcription_jobs as tj
from role_builder.db_helpers import transcription_keys as tk
from role_builder.services.acquisition import auto_select

log = structlog.get_logger(__name__)


async def handle_scraper_event(
    event: dict[str, Any],
    job: dict[str, Any],
    *,
    pool: asyncpg.Pool,
) -> None:
    """Dispatch a single scraper event to the appropriate db_helper(s)."""
    etype = event.get("type")

    if etype == "started":
        log.info(
            "scraper.started",
            job_id=str(job["id"]),
            task_id=event.get("task_id"),
        )
        return

    if etype == "progress":
        log.info(
            "scraper.progress",
            job_id=str(job["id"]),
            item_id=event.get("item_id"),
            phase=event.get("phase"),
            percent=event.get("percent"),
        )
        return

    if etype == "discovered":
        items = event.get("items") or []
        total = event.get("total", len(items))
        log.info(
            "scraper.discovered",
            job_id=str(job["id"]),
            total=total,
            count=len(items),
        )
        await si.insert_source_items_bulk(
            items,
            source_id=job["source_id"],
            tenant_id=job["tenant_id"],
            pool=pool,
        )
        await sm.update_source_status(
            job["source_id"],
            "discovered",
            discovered_count=total,
            pool=pool,
        )

        # Branche la couche requête (façade MCP roles__*) sur le pipeline
        # existant : si cette source a une acquisition_request (V2), on
        # applique sa sélection auto ou on la marque 'discovered'. Sources
        # V1 (pas de requête) : comportement inchangé, rien de plus.
        request = await ar.get_by_source_id(job["source_id"], pool=pool)
        if request is not None:
            await auto_select.on_discovery_complete(
                request,
                source_id=job["source_id"],
                tenant_id=job["tenant_id"],
                pool=pool,
            )
        return

    if etype == "item_done":
        await _handle_item_done(event, job, pool=pool)
        return

    if etype == "item_failed":
        await si.update_source_item_status(
            job["source_id"],
            event["item_id"],
            "failed",
            error=event.get("error"),
            pool=pool,
        )
        return

    if etype == "complete":
        log.info(
            "scraper.complete",
            job_id=str(job["id"]),
            downloaded=event.get("downloaded"),
            failed=event.get("failed"),
        )
        return

    if etype == "error":
        log.warning(
            "scraper.error",
            job_id=str(job["id"]),
            message=event.get("message"),
        )
        return

    if etype in ("_invalid_line", "_exit"):
        log.warning("scraper.internal_event", payload=event)
        return

    log.warning("scraper.unknown_event", job_id=str(job["id"]), payload=event)


async def _handle_item_done(
    event: dict[str, Any],
    job: dict[str, Any],
    *,
    pool: asyncpg.Pool,
) -> None:
    """Sur `item_done` : enqueue un transcription_job + bascule l'item à
    'queued_transcription'.

    Worker_pool_id :
      - `user_<user_id>` si le user a une primary key transcription active
      - `shared_default` sinon (faster-whisper sur pve2)
    """
    platform_item_id = event["item_id"]
    audio_s3_key = event.get("audio_s3_key")

    source = await sm.get_source(job["source_id"], pool=pool)
    role_project_id = source.get("role_project_id") if source else None
    user_id = (
        await rp.get_user_id_for_project(role_project_id, pool=pool)
        if role_project_id is not None
        else None
    )

    worker_pool_id = "shared_default"
    if user_id is not None:
        primary_key = await tk.get_primary_key(user_id, pool=pool)
        if primary_key is not None:
            worker_pool_id = f"user_{user_id}"

    item_row = await si.get_by_platform_id(job["source_id"], platform_item_id, pool=pool)
    if item_row is None:
        log.error(
            "scraper.item_done_lookup_failed",
            job_id=str(job["id"]),
            source_id=str(job["source_id"]),
            platform_item_id=platform_item_id,
        )
        return

    if audio_s3_key:
        await tj.insert_job(
            source_item_id=item_row["id"],
            tenant_id=item_row.get("tenant_id") or job["tenant_id"],
            audio_s3_key=audio_s3_key,
            language=event.get("language"),
            worker_pool_id=worker_pool_id,
            priority=int(event.get("priority", 0) or 0),
            pool=pool,
        )
        log.info(
            "scraper.transcription_job_queued",
            job_id=str(job["id"]),
            source_item_id=str(item_row["id"]),
            worker_pool_id=worker_pool_id,
        )

    await si.update_source_item_status(
        job["source_id"],
        platform_item_id,
        "queued_transcription",
        audio_s3_key=audio_s3_key,
        pool=pool,
    )
