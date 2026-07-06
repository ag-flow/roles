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
from role_builder.services.acquisition.upload import media_types


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
    if request["status"] == "cancelled":
        raise AcquisitionError(
            "ALREADY_CANCELLED", f"request {request_key!r} is cancelled — cannot retry"
        )

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
        # Item upload : jamais de scraper download (pas d'URL à télécharger, et
        # l'image agflow-scraper-upload n'existe pas). On relance l'extraction
        # (vidéo, objet brut conservé après échec) ou la transcription (audio).
        if request["kind"] == "upload":
            await _retry_upload_item(row, pool=pool)
            retried += 1
            continue
        # Teste le job actif AVANT le reset : sinon un item déjà couvert par un
        # download en vol serait remis `pending_download` sans nouveau job, ni
        # `failed` ni réellement en vol (BUG-26).
        if await scraping_jobs_helper.get_active_job_for_item(row["id"], "download", pool=pool):
            continue  # un job est déjà en vol pour cet item (idempotence)
        await source_items_helper.reset_for_retry(source_id, row["platform_item_id"], pool=pool)
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


async def _retry_upload_item(row: dict, *, pool: asyncpg.Pool) -> None:
    """Relance un item upload `failed` sans passer par le scraper.

    Vidéo : retour en `pending_extraction`, le worker d'extraction re-tente le
    ffmpeg (l'objet brut est conservé après un échec d'extraction). Audio :
    l'objet uploadé EST l'audio — retour en queue de transcription avec un
    nouveau job (intention de retry).
    """
    media_type = row.get("upload_media_type")
    if media_type and media_types.is_video(media_type):
        await source_items_helper.update_source_item_status(
            row["source_id"], row["platform_item_id"], "pending_extraction", pool=pool
        )
        return
    audio_key = row.get("audio_s3_key") or row["upload_s3_key"]
    await source_items_helper.update_source_item_status(
        row["source_id"], row["platform_item_id"], "audio_ready",
        audio_s3_key=audio_key, pool=pool,
    )
    await transcription_jobs_helper.insert_job(
        source_item_id=row["id"],
        tenant_id=row["tenant_id"],
        audio_s3_key=audio_key,
        worker_pool_id="shared_default",
        pool=pool,
    )
    await source_items_helper.update_source_item_status(
        row["source_id"], row["platform_item_id"], "queued_transcription", pool=pool
    )


async def _count_deposited(source_id: UUID, *, pool: asyncpg.Pool) -> int:
    rows = await source_items_helper.count_by_status(source_id, pool=pool)
    return sum(row["n"] for row in rows if row["status"] == "deposited")
