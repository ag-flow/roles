"""roles__cancel_request / roles__retry_failed — administration (spec §2.5)."""

from __future__ import annotations

from uuid import UUID

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import deposit_queue
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.db_helpers import transcription_jobs as transcription_jobs_helper
from role_builder.services.acquisition.errors import AcquisitionError


async def cancel_request(
    request_key: str, note: str | None, *, pool: asyncpg.Pool
) -> dict[str, int]:
    """Annule les jobs pending/claimed ; les items déjà déposés restent intacts."""
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")
    if request["status"] == "cancelled":
        raise AcquisitionError("ALREADY_CANCELLED", f"{request_key!r} is already cancelled")

    source_id = request["source_id"]
    cancelled_scraping = (
        await scraping_jobs_helper.cancel_pending_claimed(source_id, pool=pool)
        if source_id
        else 0
    )
    cancelled_transcription = (
        await transcription_jobs_helper.cancel_pending_claimed(source_id, pool=pool)
        if source_id
        else 0
    )
    deposited_kept = await _count_deposited(source_id, pool=pool) if source_id else 0

    await ar.update_status(request_key, "cancelled", pool=pool)

    return {
        "cancelled_jobs": cancelled_scraping + cancelled_transcription,
        "deposited_kept": deposited_kept,
    }


async def retry_failed(
    request_key: str, item_ids: list[UUID] | None, *, pool: asyncpg.Pool
) -> dict[str, int]:
    """Re-queue les items `failed` (tous, ou une sélection) — réinsère un download job."""
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None:
        raise AcquisitionError("UNKNOWN_REQUEST", f"no acquisition request {request_key!r}")

    source_id = request["source_id"]
    source = await sources_helper.get_source(source_id, pool=pool) if source_id else None
    failed_rows = (
        await source_items_helper.list_items_by_source(
            source_id, status="failed", limit=10_000, offset=0, pool=pool
        )
        if source_id
        else []
    )
    if item_ids is not None:
        wanted = set(item_ids)
        failed_rows = [row for row in failed_rows if row["id"] in wanted]

    retried = 0
    for row in failed_rows:
        # Échec au dépôt docflow (transcript déjà dans MinIO) : l'item repart
        # en 'transcribed' pour le worker de dépôt — pas de re-download (§6 l.7).
        if row.get("transcript_s3_key"):
            await deposit_queue.reset_failed_deposit(row["id"], pool=pool)
            retried += 1
            continue
        await source_items_helper.reset_for_retry(source_id, row["platform_item_id"], pool=pool)
        if await scraping_jobs_helper.get_active_job_for_item(row["id"], "download", pool=pool):
            continue  # un job est déjà en vol pour cet item (idempotence)
        await scraping_jobs_helper.insert_job(
            source_id=source_id,
            source_item_id=row["id"],
            tenant_id=request["tenant_id"],
            command="download",
            credentials_id=source.get("credentials_id") if source else None,
            priority=0,
            pool=pool,
        )
        retried += 1

    return {"retried_count": retried}


async def _count_deposited(source_id: UUID, *, pool: asyncpg.Pool) -> int:
    rows = await source_items_helper.count_by_status(source_id, pool=pool)
    return sum(row["n"] for row in rows if row["status"] == "deposited")
