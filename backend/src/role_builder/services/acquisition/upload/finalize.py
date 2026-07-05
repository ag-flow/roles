"""roles__finalize_upload — vérification de l'objet MinIO et entrée dans le
pipeline standard (spec §2.2, §3).

Après le PUT client : l'objet est vérifié, l'audio est extrait si le média
est une vidéo, l'item passe en `audio_ready` puis est mis en queue de
transcription — exactement le chemin d'un item scrapé après `item_done`
(event_handlers._handle_item_done), pour qu'aucun composant aval n'ait de
cas spécial upload. Queue partagée `shared_default` : les sources upload
n'ont pas de role_project, donc pas de clé SaaS utilisateur (même règle que
les sources V2 scrapées).
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import source_items_upload as siu
from role_builder.db_helpers import transcription_jobs as transcription_jobs_helper
from role_builder.services import minio_client as minio_client_module
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.upload import media_types
from role_builder.services.acquisition.upload.audio_extraction import (
    AudioExtractionError,
    extract_audio_to_mp3,
)
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.minio_client import MinioWrapper

log = structlog.get_logger(__name__)


async def finalize_upload(
    *,
    request_key: str,
    item_id: UUID,
    now: datetime,
    pool: asyncpg.Pool,
    minio: MinioWrapper | None = None,
) -> dict[str, Any]:
    """Vérifie le PUT, extrait l'audio si vidéo, met l'item en pipeline.

    Idempotent : un item déjà finalisé retourne son statut courant.

    Raises:
        AcquisitionError(UNKNOWN_REQUEST | UPLOAD_NOT_FOUND | UPLOAD_EXPIRED
        | AUDIO_EXTRACTION_FAILED)
    """
    minio = minio or minio_client_module.minio_client
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None or request["kind"] != "upload":
        raise AcquisitionError("UNKNOWN_REQUEST", f"no upload request {request_key!r}")

    item = await source_items_helper.get_by_id(item_id, pool=pool)
    if item is None or item["source_id"] != request["source_id"]:
        raise AcquisitionError(
            "UPLOAD_NOT_FOUND", f"no upload slot {item_id} on request {request_key!r}"
        )
    if item["status"] != "awaiting_upload":
        return {"item_id": item_id, "status": item["status"]}

    if item["upload_expires_at"] < now:
        await _cleanup_expired_item(item, minio=minio, pool=pool)
        raise AcquisitionError(
            "UPLOAD_EXPIRED",
            f"upload slot {item_id} expired at {item['upload_expires_at'].isoformat()}",
        )

    upload_key = item["upload_s3_key"]
    if not await asyncio.to_thread(minio.object_exists, AUDIO_BUCKET, upload_key):
        raise AcquisitionError(
            "UPLOAD_NOT_FOUND",
            f"no object at {AUDIO_BUCKET}/{upload_key} — PUT missing or not finished",
        )

    audio_key = await _resolve_audio_key(item, minio=minio, pool=pool)
    await source_items_helper.update_source_item_status(
        item["source_id"], item["platform_item_id"], "audio_ready",
        audio_s3_key=audio_key, pool=pool,
    )
    await transcription_jobs_helper.insert_job(
        source_item_id=item_id,
        tenant_id=item["tenant_id"],
        audio_s3_key=audio_key,
        worker_pool_id="shared_default",
        pool=pool,
    )
    await source_items_helper.update_source_item_status(
        item["source_id"], item["platform_item_id"], "queued_transcription", pool=pool
    )
    log.info(
        "upload.finalized",
        request_key=request_key,
        item_id=str(item_id),
        audio_s3_key=audio_key,
    )
    return {"item_id": item_id, "status": "queued_transcription"}


async def _resolve_audio_key(
    item: dict[str, Any], *, minio: MinioWrapper, pool: asyncpg.Pool
) -> str:
    """Clé audio de l'item : l'objet uploadé tel quel, ou l'extrait mp3 si vidéo."""
    upload_key = item["upload_s3_key"]
    if not media_types.is_video(item["upload_media_type"]):
        return upload_key

    audio_key = upload_key.rsplit(".", 1)[0] + ".mp3"
    try:
        await extract_audio_to_mp3(
            minio, bucket=AUDIO_BUCKET, source_key=upload_key, target_key=audio_key
        )
    except AudioExtractionError as exc:
        await source_items_helper.update_source_item_status(
            item["source_id"], item["platform_item_id"], "failed",
            error=f"AUDIO_EXTRACTION_FAILED: {exc}", pool=pool,
        )
        raise AcquisitionError("AUDIO_EXTRACTION_FAILED", str(exc)) from exc

    # Seul l'audio est conservé ; l'objet vidéo brut est supprimé (best-effort).
    try:
        await asyncio.to_thread(minio.remove_object, AUDIO_BUCKET, upload_key)
    except Exception:  # noqa: BLE001 — un brut orphelin ne bloque pas le pipeline
        log.warning("upload.raw_video_cleanup_failed", key=upload_key)
    return audio_key


async def _cleanup_expired_item(
    item: dict[str, Any], *, minio: MinioWrapper, pool: asyncpg.Pool
) -> None:
    """Nettoie un slot expiré : objet best-effort, puis ligne source_items."""
    try:
        await asyncio.to_thread(minio.remove_object, AUDIO_BUCKET, item["upload_s3_key"])
    except Exception:  # noqa: BLE001 — le cleanup périodique repassera
        log.warning("upload.expired_object_cleanup_failed", key=item["upload_s3_key"])
    await siu.delete_item(item["id"], pool=pool)
