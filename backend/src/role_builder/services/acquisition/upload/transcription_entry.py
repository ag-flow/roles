"""Entrée d'un item upload dans le pipeline de transcription (spec §2.2, §3).

Étape commune au `finalize_upload` d'un média audio (pas d'extraction) et au
worker d'extraction après ffmpeg d'un média vidéo : l'item passe `audio_ready`,
un `transcription_job` est enqueué en queue partagée, puis l'item passe
`queued_transcription` — exactement le chemin d'un item scrapé après
`item_done` (event_handlers._handle_item_done), pour qu'aucun composant aval
n'ait de cas spécial upload.
"""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
import structlog

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import transcription_jobs as transcription_jobs_helper
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.minio_client import MinioWrapper

log = structlog.get_logger(__name__)


async def enter_transcription_pipeline(
    item: dict[str, Any],
    *,
    audio_key: str,
    pool: asyncpg.Pool,
    minio: MinioWrapper,
    remove_raw_key: str | None = None,
) -> None:
    """Passe un item à `queued_transcription` avec son job de transcription.

    Idempotent : si un job existe déjà pour l'item (reprise crash), aucun
    second job n'est inséré. `remove_raw_key` (l'objet vidéo brut) est
    supprimé en best-effort après l'entrée en pipeline.
    """
    await source_items_helper.update_source_item_status(
        item["source_id"], item["platform_item_id"], "audio_ready",
        audio_s3_key=audio_key, pool=pool,
    )
    if not await transcription_jobs_helper.has_job_for_item(item["id"], pool=pool):
        await transcription_jobs_helper.insert_job(
            source_item_id=item["id"],
            tenant_id=item["tenant_id"],
            audio_s3_key=audio_key,
            worker_pool_id="shared_default",
            pool=pool,
        )
    await source_items_helper.update_source_item_status(
        item["source_id"], item["platform_item_id"], "queued_transcription", pool=pool
    )
    if remove_raw_key is not None:
        # Seul l'audio est conservé ; l'objet vidéo brut est supprimé
        # (best-effort — un brut orphelin ne bloque pas le pipeline).
        try:
            await asyncio.to_thread(minio.remove_object, AUDIO_BUCKET, remove_raw_key)
        except Exception:  # noqa: BLE001
            log.warning("upload.raw_video_cleanup_failed", key=remove_raw_key)
