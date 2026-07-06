"""CRUD asyncpg pour la table `source_items` (cf. migration 0003).

`insert_source_items_bulk` utilise `executemany` avec `ON CONFLICT DO NOTHING`
sur la contrainte UNIQUE `(source_id, platform_item_id)` pour idempotence.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO source_items
        (source_id, tenant_id, platform_item_id, title, duration_s,
         published_at, thumbnail_url, status, description_excerpt, tags)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
    ON CONFLICT (source_id, platform_item_id) DO NOTHING
"""


async def insert_source_items_bulk(
    items: list[dict[str, Any]],
    *,
    source_id: UUID,
    tenant_id: UUID,
    pool: asyncpg.Pool,
) -> int:
    """Bulk-insert items. Returns the count we attempted to insert.

    Items keys: id (=> platform_item_id), title, duration_s,
    published_at, thumbnail_url, description_excerpt (optionnel),
    tags (optionnel, list[str]). Status forced to 'pending_download'.
    Idempotent via ON CONFLICT DO NOTHING.
    """
    if not items:
        return 0

    rows = [
        (
            source_id,
            tenant_id,
            item["id"],
            item.get("title"),
            item.get("duration_s"),
            item.get("published_at"),
            item.get("thumbnail_url"),
            "pending_download",
            item.get("description_excerpt"),
            item.get("tags"),
        )
        for item in items
    ]
    async with pool.acquire() as conn:
        await conn.executemany(_INSERT_SQL, rows)
    return len(rows)


async def get_by_platform_id(
    source_id: UUID,
    platform_item_id: str,
    *,
    pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Lookup un source_item par sa clé naturelle (source_id, platform_item_id)."""
    query = "SELECT * FROM source_items WHERE source_id = $1 AND platform_item_id = $2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, source_id, platform_item_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def get_by_id(item_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Fetch un source_item par son id ; renvoie ``None`` si absent."""
    query = "SELECT * FROM source_items WHERE id = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, item_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def list_by_project(
    role_project_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List source_items d'un projet (toutes sources confondues), récents d'abord."""
    query = (
        "SELECT si.* FROM source_items si "
        "JOIN sources s ON s.id = si.source_id "
        "WHERE s.role_project_id = $1 "
        "ORDER BY si.published_at DESC NULLS LAST, si.id ASC "
        "LIMIT $2 OFFSET $3"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, role_project_id, limit, offset)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def update_source_item_status(
    source_id: UUID,
    platform_item_id: str,
    status: str,
    *,
    audio_s3_key: str | None = None,
    transcript_s3_key: str | None = None,
    error: str | None = None,
    pool: asyncpg.Pool,
) -> None:
    """Update status (+ optional s3 keys / error) for a (source_id, platform_item_id)."""
    query = """
        UPDATE source_items
        SET status = $1,
            audio_s3_key = COALESCE($2, audio_s3_key),
            transcript_s3_key = COALESCE($3, transcript_s3_key),
            error = COALESCE($4, error),
            updated_at = now()
        WHERE source_id = $5 AND platform_item_id = $6
    """
    async with pool.acquire() as conn:
        await conn.execute(
            query, status, audio_s3_key, transcript_s3_key, error, source_id, platform_item_id
        )


async def list_items_by_source(
    source_id: UUID,
    *,
    min_duration_s: int | None = None,
    max_duration_s: int | None = None,
    since_date: datetime | None = None,
    until_date: datetime | None = None,
    title_contains: str | None = None,
    status: str | None = None,
    selected: bool | None = None,
    limit: int = 50,
    offset: int = 0,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List items of a source with optional filters; ordered by published_at desc."""
    clauses = ["source_id = $1"]
    params: list[Any] = [source_id]

    if min_duration_s is not None:
        params.append(min_duration_s)
        clauses.append(f"duration_s >= ${len(params)}")
    if max_duration_s is not None:
        params.append(max_duration_s)
        clauses.append(f"duration_s <= ${len(params)}")
    if since_date is not None:
        params.append(since_date)
        clauses.append(f"published_at >= ${len(params)}")
    if until_date is not None:
        params.append(until_date)
        clauses.append(f"published_at <= ${len(params)}")
    if title_contains is not None:
        params.append(f"%{title_contains}%")
        clauses.append(f"title ILIKE ${len(params)}")
    if status is not None:
        params.append(status)
        clauses.append(f"status = ${len(params)}")
    if selected is not None:
        params.append(selected)
        clauses.append(f"selected = ${len(params)}")

    params.append(limit)
    limit_idx = len(params)
    params.append(offset)
    offset_idx = len(params)

    where = " AND ".join(clauses)
    # Tie-breaker `id` : sans lui, l'ordre entre ex æquo (dates à précision
    # jour, uploads published_at NULL) n'est pas garanti par Postgres → un item
    # apparaîtrait sur deux pages et un autre jamais entre deux appels (BUG-15).
    query = (
        "SELECT * FROM source_items "
        f"WHERE {where} "
        "ORDER BY published_at DESC NULLS LAST, id ASC "
        f"LIMIT ${limit_idx} OFFSET ${offset_idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_items_by_ids(
    source_id: UUID, item_ids: list[UUID], *, pool: asyncpg.Pool
) -> list[dict[str, Any]]:
    """Items de `source_id` dont l'id est dans `item_ids` (validation d'appartenance).

    Permet de rejeter les item_ids inconnus ou d'une autre source avant toute
    écriture (pas de job download pour un item hors périmètre, pas de FK 500).
    """
    if not item_ids:
        return []
    query = "SELECT * FROM source_items WHERE source_id = $1 AND id = ANY($2::uuid[])"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, source_id, item_ids)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def count_by_status(source_id: UUID, *, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Compte les items d'une source groupés par (status, selected).

    Base des `counts` de roles__request_status (§2.3) — repliés côté
    service (pas de mapping vers le vocabulaire de statuts exposé ici).
    """
    query = """
        SELECT status, selected, count(*) AS n
        FROM source_items
        WHERE source_id = $1
        GROUP BY status, selected
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, source_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def reset_for_retry(
    source_id: UUID, platform_item_id: str, *, pool: asyncpg.Pool
) -> None:
    """Remet un item `failed` à `pending_download`, efface l'erreur (roles__retry_failed)."""
    query = """
        UPDATE source_items
        SET status = 'pending_download', error = NULL, updated_at = now()
        WHERE source_id = $1 AND platform_item_id = $2
    """
    async with pool.acquire() as conn:
        await conn.execute(query, source_id, platform_item_id)


async def select_items(
    source_id: UUID,
    item_ids: list[UUID],
    *,
    deselect_others: bool = False,
    pool: asyncpg.Pool,
) -> int:
    """Mark item_ids as selected. If deselect_others, sets others to false first."""
    async with pool.acquire() as conn:
        if deselect_others:
            await conn.execute(
                "UPDATE source_items "
                "SET selected = false, updated_at = now() "
                "WHERE source_id = $1 AND NOT (id = ANY($2::uuid[]))",
                source_id,
                item_ids,
            )
        result = await conn.execute(
            "UPDATE source_items "
            "SET selected = true, updated_at = now() "
            "WHERE source_id = $1 AND id = ANY($2::uuid[])",
            source_id,
            item_ids,
        )
    # Nombre réel de lignes sélectionnées (pas len(item_ids)) : des ids inconnus,
    # d'une autre source ou en double ne gonflent pas le compteur (BUG-13).
    parts = result.split()
    if len(parts) >= 2 and parts[0].upper() == "UPDATE":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0
