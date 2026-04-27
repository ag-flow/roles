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

from role_builder.db_helpers import source_items as si
from role_builder.db_helpers import sources as sm

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
        return

    if etype == "item_done":
        await si.update_source_item_status(
            job["source_id"],
            event["item_id"],
            "audio_ready",
            audio_s3_key=event.get("audio_s3_key"),
            pool=pool,
        )
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
