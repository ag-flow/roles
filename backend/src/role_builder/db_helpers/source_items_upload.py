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
