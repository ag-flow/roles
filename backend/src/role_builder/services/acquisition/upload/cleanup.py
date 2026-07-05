"""Nettoyage périodique des slots d'upload expirés (spec §5.5).

Job léger appelé par le scheduler (cf. services/scheduler.py) : supprime
les items `awaiting_upload` dont le TTL est dépassé, et l'objet MinIO
orphelin le cas échéant (PUT fait mais jamais finalisé). Un item entré en
pipeline (`audio_ready` et au-delà) n'est jamais touché.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import asyncpg
import structlog

from role_builder.db_helpers import source_items_upload as siu
from role_builder.services import minio_client as minio_client_module
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.minio_client import MinioWrapper

log = structlog.get_logger(__name__)


async def cleanup_expired_slots(
    *,
    now: datetime,
    pool: asyncpg.Pool,
    minio: MinioWrapper | None = None,
) -> int:
    """Supprime les slots expirés (item + objet best-effort) ; retourne le compte."""
    minio = minio or minio_client_module.minio_client
    expired = await siu.list_expired_awaiting_upload(now, pool=pool)
    removed = 0
    for item in expired:
        try:
            await asyncio.to_thread(minio.remove_object, AUDIO_BUCKET, item["upload_s3_key"])
        except Exception:  # noqa: BLE001 — item conservé, retenté au prochain run
            log.warning("upload.cleanup_object_failed", key=item["upload_s3_key"])
            continue
        await siu.delete_item(item["id"], pool=pool)
        removed += 1
        log.info(
            "upload.slot_cleaned",
            item_id=str(item["id"]),
            expired_at=item["upload_expires_at"].isoformat(),
        )
    return removed
