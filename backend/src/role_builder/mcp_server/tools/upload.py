"""Adaptateurs MCP — cycle upload direct (spec v2/01-protocole-mcp.md §2.2).

Couche fine, même modèle que submission.py : résout `tenant_id`/horloge/
`pool`/MinIO, délègue aux services `services.acquisition.upload.*`, et
convertit `AcquisitionError` en enveloppe `{"error": {...}}` (§5.6).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from role_builder.config import TENANT_ID_DEFAULT
from role_builder.db import db_pool
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.upload import finalize as finalize_service
from role_builder.services.acquisition.upload import intake as intake_service


async def create_upload_request(
    title: str,
    *,
    submitted_by: str,
    docflow_target: dict[str, Any] | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Ouvre une requête d'acquisition de type upload.

    Pour les médias hors plateformes (enregistrements perso, conférences,
    podcasts fournis en fichier). Retourne `{request_key, status}`.
    """
    try:
        return await intake_service.create_upload_request(
            title=title,
            submitted_by=submitted_by,
            tenant_id=TENANT_ID_DEFAULT,
            docflow_target=docflow_target,
            note=note,
            today=datetime.now(UTC).date(),
            pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()


async def request_upload_slot(
    request_key: str,
    *,
    filename: str,
    media_type: str,
    title: str | None = None,
    published_at: str | None = None,
    duration_s: int | None = None,
) -> dict[str, Any]:
    """Crée un item et un slot d'upload : URL présignée PUT MinIO, TTL 1 h.

    Le fichier ne transite jamais par MCP : PUT direct du client sur
    `upload_url`. Retourne `{item_id, upload_url, expires_at}`.
    """
    try:
        return await intake_service.request_upload_slot(
            request_key=request_key,
            filename=filename,
            media_type=media_type,
            title=title,
            published_at=published_at,
            duration_s=duration_s,
            now=datetime.now(UTC),
            pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()


async def finalize_upload(request_key: str, *, item_id: str) -> dict[str, Any]:
    """Après le PUT réussi : vérifie l'objet MinIO, passe l'item en pipeline.

    Extraction audio ffmpeg si le média est une vidéo, puis transcription →
    dépôt docflow, strictement identique aux items scrapés.
    """
    try:
        return await finalize_service.finalize_upload(
            request_key=request_key,
            item_id=_parse_item_id(item_id),
            now=datetime.now(UTC),
            pool=db_pool.pool,
        )
    except AcquisitionError as exc:
        return exc.to_dict()


async def close_upload_request(request_key: str) -> dict[str, Any]:
    """Ferme l'intake (plus de nouveaux slots) ; la complétion suit les items en cours."""
    try:
        return await intake_service.close_upload_request(request_key=request_key, pool=db_pool.pool)
    except AcquisitionError as exc:
        return exc.to_dict()


def _parse_item_id(item_id: str) -> UUID:
    try:
        return UUID(str(item_id))
    except ValueError as exc:
        raise AcquisitionError(
            "UPLOAD_NOT_FOUND", f"item_id {item_id!r} is not a valid UUID"
        ) from exc
