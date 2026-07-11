"""roles__create_upload_request / roles__request_upload_slot /
roles__close_upload_request — intake par upload direct (spec §2.2).

Le fichier ne transite jamais par MCP : le slot fournit une URL présignée
PUT sur MinIO `corpus-audio`, TTL 1 h. L'item attend en `awaiting_upload`
jusqu'au finalize (cf. finalize.py) ou au nettoyage périodique (cleanup.py).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import asyncpg

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items_upload as siu
from role_builder.db_helpers import sources as sources_helper
from role_builder.services import minio_client as minio_client_module
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.request_creation import insert_request_with_retry
from role_builder.services.acquisition.request_key import build_request_key_base
from role_builder.services.acquisition.upload import media_types
from role_builder.services.minio_client import MinioWrapper

AUDIO_BUCKET = "corpus-audio"
SLOT_TTL_S = 3600  # TTL des URL présignées PUT (spec §2.2 : 1 h)


async def create_upload_request(
    *,
    title: str,
    submitted_by: str,
    tenant_id: UUID,
    docflow_target: dict[str, Any] | None = None,
    note: str | None = None,
    today: date,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    """Ouvre une requête d'acquisition kind=upload (statut `open_for_upload`).

    Les items sont rattachés à une source technique `platform='upload'`
    sans URL (spec §4) ; `title` sert de hint lisible au request_key.
    """
    source_id = await sources_helper.insert_source(
        tenant_id=tenant_id,
        platform="upload",
        source_type="upload",
        url=None,
        pool=pool,
    )
    base_key = build_request_key_base("upload", "", note=title, today=today)
    request_key = await insert_request_with_retry(
        base_key,
        tenant_id=tenant_id,
        submitted_by=submitted_by,
        kind="upload",
        source_id=source_id,
        mode=None,
        filters=None,
        docflow_target=docflow_target,
        note=note,
        status="open_for_upload",
        pool=pool,
    )
    return {"request_key": request_key, "status": "open_for_upload"}


async def request_upload_slot(
    *,
    request_key: str,
    filename: str,
    media_type: str,
    title: str | None = None,
    published_at: str | None = None,
    duration_s: int | None = None,
    now: datetime,
    ttl_s: int = SLOT_TTL_S,
    pool: asyncpg.Pool,
    minio: MinioWrapper | None = None,
) -> dict[str, Any]:
    """Crée un item `awaiting_upload` et son URL présignée PUT.

    Raises:
        AcquisitionError(UNKNOWN_REQUEST | REQUEST_CLOSED | UNSUPPORTED_MEDIA
        | INVALID_PUBLISHED_AT)
    """
    minio = minio or minio_client_module.minio_client
    request = await _get_upload_request(request_key, pool=pool)
    if request["status"] != "open_for_upload":
        raise AcquisitionError(
            "REQUEST_CLOSED", f"request {request_key!r} no longer accepts upload slots"
        )
    if not media_types.is_supported(media_type):
        raise AcquisitionError(
            "UNSUPPORTED_MEDIA",
            f"media_type {media_type!r} is not accepted",
            details={"supported": media_types.supported_types()},
        )

    item_id = uuid4()
    upload_s3_key = f"upload/{request_key}/{item_id}{media_types.extension_for(media_type)}"
    expires_at = now + timedelta(seconds=ttl_s)
    await siu.insert_awaiting_upload_item(
        item_id=item_id,
        source_id=request["source_id"],
        tenant_id=request["tenant_id"],
        platform_item_id=f"upload-{item_id.hex[:12]}",
        title=title or filename,
        duration_s=duration_s,
        published_at=_parse_published_at(published_at),
        upload_media_type=media_type,
        upload_s3_key=upload_s3_key,
        upload_expires_at=expires_at,
        pool=pool,
    )
    upload_url = await asyncio.to_thread(
        minio.presigned_put_url, AUDIO_BUCKET, upload_s3_key, expires_seconds=ttl_s
    )
    return {"item_id": item_id, "upload_url": upload_url, "expires_at": expires_at.isoformat()}


async def close_upload_request(*, request_key: str, pool: asyncpg.Pool) -> dict[str, Any]:
    """Ferme l'intake (plus de nouveaux slots) ; idempotent.

    La complétion suit les items en cours : le statut stocké passe à
    `acquiring`, `completed`/`partially_failed` restent dérivés à la lecture.
    """
    request = await _get_upload_request(request_key, pool=pool)
    if request["status"] == "open_for_upload":
        await ar.update_status(request_key, "acquiring", pool=pool)
        return {"request_key": request_key, "status": "acquiring"}
    return {"request_key": request_key, "status": request["status"]}


async def _get_upload_request(request_key: str, *, pool: asyncpg.Pool) -> dict[str, Any]:
    """Résout une requête kind=upload ; UNKNOWN_REQUEST sinon (y compris scrape)."""
    request = await ar.get_by_key(request_key, pool=pool)
    if request is None or request["kind"] != "upload":
        raise AcquisitionError("UNKNOWN_REQUEST", f"no upload request {request_key!r}")
    return request


def _parse_published_at(published_at: str | None) -> datetime | None:
    if published_at is None:
        return None
    try:
        return datetime.fromisoformat(published_at)
    except ValueError as exc:
        raise AcquisitionError(
            "INVALID_PUBLISHED_AT",
            f"published_at {published_at!r} is not an ISO 8601 timestamp",
        ) from exc
