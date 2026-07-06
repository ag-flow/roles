"""Accès asyncpg à `source_items` propre au cycle upload (cf. migration 0008).

Séparé de `source_items.py` (SRP + limite de taille de fichier) : ces
fonctions ne servent que l'intake par upload direct (spec v2/01 §2.2, §5.5) —
slot `awaiting_upload`, nettoyage des slots expirés.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO source_items
        (id, source_id, tenant_id, platform_item_id, title, duration_s,
         published_at, status, selected, upload_media_type, upload_s3_key,
         upload_expires_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7, 'awaiting_upload', true, $8, $9, $10)
"""


async def insert_awaiting_upload_item(
    *,
    item_id: UUID,
    source_id: UUID,
    tenant_id: UUID,
    platform_item_id: str,
    title: str,
    duration_s: int | None,
    published_at: datetime | None,
    upload_media_type: str,
    upload_s3_key: str,
    upload_expires_at: datetime,
    pool: asyncpg.Pool,
) -> None:
    """Insère un slot d'upload : item `awaiting_upload`, d'emblée `selected`.

    `id` est fourni par l'appelant (pas généré en base) : la clé objet MinIO
    du slot (`upload_s3_key`) contient l'item_id, il doit donc exister avant
    l'INSERT.
    """
    async with pool.acquire() as conn:
        await conn.execute(
            _INSERT_SQL,
            item_id,
            source_id,
            tenant_id,
            platform_item_id,
            title,
            duration_s,
            published_at,
            upload_media_type,
            upload_s3_key,
            upload_expires_at,
        )


async def list_expired_awaiting_upload(
    now: datetime, *, pool: asyncpg.Pool
) -> list[dict[str, Any]]:
    """Slots `awaiting_upload` dont le TTL est dépassé (index partiel 0008)."""
    query = """
        SELECT * FROM source_items
        WHERE status = 'awaiting_upload' AND upload_expires_at < $1
        ORDER BY upload_expires_at ASC
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, now)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def delete_item(item_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Supprime un slot nettoyé (jamais utilisé sur un item entré en pipeline)."""
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM source_items WHERE id = $1", item_id)


async def claim_finalize_slot(
    item_id: UUID,
    *,
    new_status: str,
    audio_s3_key: str | None = None,
    pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Sort atomiquement un slot de `awaiting_upload` vers `new_status`.

    Claim conditionnel : la ligne n'est mise à jour que si elle est encore
    `awaiting_upload`. Deux `finalize_upload` concurrents ne peuvent donc pas
    entrer tous les deux en pipeline — le second reçoit ``None`` (BUG-20). Un
    slot ainsi claimé n'est plus `awaiting_upload`, donc hors de portée du
    nettoyage périodique (BUG-21).
    """
    query = """
        UPDATE source_items
        SET status = $2,
            audio_s3_key = COALESCE($3, audio_s3_key),
            updated_at = now()
        WHERE id = $1 AND status = 'awaiting_upload'
        RETURNING *
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, item_id, new_status, audio_s3_key)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def claim_next_for_extraction(*, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Claim FIFO le prochain item `pending_extraction` → `extracting_audio`.

    Même pattern que la queue de dépôt (FOR UPDATE SKIP LOCKED) : un seul
    worker d'extraction par déploiement (cf. requeue_stale_extracting).
    """
    query = """
        UPDATE source_items
        SET status = 'extracting_audio', updated_at = now()
        WHERE id = (
            SELECT id FROM source_items
            WHERE status = 'pending_extraction'
            ORDER BY updated_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING *
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def requeue_stale_extracting(*, pool: asyncpg.Pool) -> int:
    """Remet les items `extracting_audio` orphelins en `pending_extraction`.

    À appeler au démarrage de la boucle d'extraction uniquement (reprise
    crash). La ré-extraction est idempotente : l'objet vidéo brut n'est
    supprimé qu'après l'entrée effective en transcription.
    """
    query = """
        UPDATE source_items
        SET status = 'pending_extraction', updated_at = now()
        WHERE status = 'extracting_audio'
    """
    async with pool.acquire() as conn:
        result = await conn.execute(query)
    parts = result.split()
    if len(parts) >= 2 and parts[0].upper() == "UPDATE":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0
