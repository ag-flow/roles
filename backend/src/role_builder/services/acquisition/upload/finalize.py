"""roles__finalize_upload — vérification de l'objet MinIO et entrée dans le
pipeline (spec §2.2, §3).

Après le PUT client, l'objet est vérifié puis le slot est claimé
atomiquement hors de `awaiting_upload` (idempotence + protection contre le
double finalize et le nettoyage concurrent) :

- média **audio** : aucune extraction, l'item passe directement en queue de
  transcription — l'appel reste court ;
- média **vidéo** : l'item passe `pending_extraction` et l'appel retourne
  immédiatement. L'extraction ffmpeg (potentiellement plusieurs minutes,
  fichier volumineux) est faite par un worker de fond (extraction_worker.py),
  jamais dans l'appel MCP — aucun tool ne bloque (spec §1.1).

Queue partagée `shared_default` : les sources upload n'ont pas de
role_project, donc pas de clé SaaS utilisateur (même règle que les sources
V2 scrapées).
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
from role_builder.services import minio_client as minio_client_module
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.upload import media_types
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from role_builder.services.acquisition.upload.transcription_entry import (
    enter_transcription_pipeline,
)
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
    """Vérifie le PUT et fait entrer l'item dans le pipeline.

    Retourne `{item_id, status}` : `queued_transcription` (audio, immédiat)
    ou `pending_extraction` (vidéo, extraction déférée au worker de fond).

    Idempotent : un item déjà finalisé retourne son statut courant.

    Raises:
        AcquisitionError(UNKNOWN_REQUEST | UPLOAD_NOT_FOUND | UPLOAD_EXPIRED)
    """
    minio = minio or minio_client_module.minio_client
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None or request["kind"] != "upload":
        raise AcquisitionError("UNKNOWN_REQUEST", f"no upload request {request_key!r}")
    if request["status"] == "cancelled":
        raise AcquisitionError(
            "ALREADY_CANCELLED", f"upload request {request_key!r} is cancelled"
        )

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

    if media_types.is_video(item["upload_media_type"]):
        return await _enqueue_extraction(item, request_key=request_key, pool=pool)
    return await _enter_pipeline_direct(
        item, upload_key=upload_key, request_key=request_key, pool=pool, minio=minio
    )


async def _enqueue_extraction(
    item: dict[str, Any], *, request_key: str, pool: asyncpg.Pool
) -> dict[str, Any]:
    """Claime le slot vidéo en `pending_extraction` ; le worker fera le ffmpeg."""
    claimed = await siu.claim_finalize_slot(
        item["id"], new_status="pending_extraction", pool=pool
    )
    if claimed is None:  # finalize concurrent : le slot a déjà été claimé.
        current = await source_items_helper.get_by_id(item["id"], pool=pool)
        return {"item_id": item["id"], "status": current["status"] if current else "unknown"}
    log.info("upload.extraction_enqueued", request_key=request_key, item_id=str(item["id"]))
    return {"item_id": item["id"], "status": "pending_extraction"}


async def _enter_pipeline_direct(
    item: dict[str, Any],
    *,
    upload_key: str,
    request_key: str,
    pool: asyncpg.Pool,
    minio: MinioWrapper,
) -> dict[str, Any]:
    """Média audio : claime le slot puis met l'item en queue de transcription."""
    claimed = await siu.claim_finalize_slot(
        item["id"], new_status="audio_ready", audio_s3_key=upload_key, pool=pool
    )
    if claimed is None:  # finalize concurrent : le slot a déjà été claimé.
        current = await source_items_helper.get_by_id(item["id"], pool=pool)
        return {"item_id": item["id"], "status": current["status"] if current else "unknown"}
    await enter_transcription_pipeline(claimed, audio_key=upload_key, pool=pool, minio=minio)
    log.info("upload.finalized", request_key=request_key, item_id=str(item["id"]),
             audio_s3_key=upload_key)
    return {"item_id": item["id"], "status": "queued_transcription"}


async def _cleanup_expired_item(
    item: dict[str, Any], *, minio: MinioWrapper, pool: asyncpg.Pool
) -> None:
    """Nettoie un slot expiré : objet best-effort, puis ligne source_items."""
    try:
        await asyncio.to_thread(minio.remove_object, AUDIO_BUCKET, item["upload_s3_key"])
    except Exception:  # noqa: BLE001 — le cleanup périodique repassera
        log.warning("upload.expired_object_cleanup_failed", key=item["upload_s3_key"])
    await siu.delete_item(item["id"], pool=pool)
