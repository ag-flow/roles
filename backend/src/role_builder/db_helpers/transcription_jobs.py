"""CRUD asyncpg pour `transcription_jobs` (cf. migration 0005).

Helpers Sprint 3 :
- insert_job : enqueue un job avec worker_pool_id (user_<uuid> ou shared_default)
- reassign_pending_to_shared : bascule worker_pool_id user_X -> shared_default
  pour les jobs encore pending (utilisé par credit_basculer sur exhausted)
- list_jobs : monitoring / debug, filtres optionnels status + worker_pool_id

Le worker côté container claim ses jobs via un SELECT FOR UPDATE SKIP LOCKED
filtré sur son worker_pool_id (cf. docker/transcription-worker/).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO transcription_jobs
        (source_item_id, tenant_id, audio_s3_key, language,
         worker_pool_id, status, priority)
    VALUES ($1, $2, $3, $4, $5, 'pending', $6)
    RETURNING id
"""


async def insert_job(
    *,
    source_item_id: UUID,
    tenant_id: UUID,
    audio_s3_key: str,
    language: str | None = None,
    worker_pool_id: str,
    priority: int = 0,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert un transcription_job pending et retourne l'id généré."""
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            _INSERT_SQL,
            source_item_id,
            tenant_id,
            audio_s3_key,
            language,
            worker_pool_id,
            priority,
        )
    return new_id  # type: ignore[no-any-return]


async def reassign_pending_to_shared(
    user_pool_id: str, *, pool: asyncpg.Pool
) -> int:
    """Bascule worker_pool_id=user_X -> 'shared_default' pour tous les jobs pending.

    Retourne le nombre de lignes modifiées. Utilisé sur exhausted/invalid d'une
    primary key — les jobs en cours ne sont pas touchés (status != 'pending').
    """
    query = (
        "UPDATE transcription_jobs "
        "SET worker_pool_id = 'shared_default', updated_at = now() "
        "WHERE worker_pool_id = $1 AND status = 'pending'"
    )
    async with pool.acquire() as conn:
        status = await conn.execute(query, user_pool_id)
    # asyncpg execute() retourne 'UPDATE <n>' pour les UPDATE
    parts = status.split()
    if len(parts) >= 2 and parts[0].upper() == "UPDATE":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0


async def list_jobs(
    *,
    status: str | None = None,
    worker_pool_id: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List transcription_jobs avec filtres optionnels (status + worker_pool_id)."""
    clauses: list[str] = []
    params: list[Any] = []

    if status is not None:
        params.append(status)
        clauses.append(f"status = ${len(params)}")
    if worker_pool_id is not None:
        params.append(worker_pool_id)
        clauses.append(f"worker_pool_id = ${len(params)}")

    params.append(limit)
    limit_idx = len(params)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses) + " "

    query = (
        "SELECT id, source_item_id, tenant_id, audio_s3_key, language, "
        "worker_pool_id, status, priority, attempts, error, "
        "created_at, started_at, completed_at "
        "FROM transcription_jobs "
        f"{where}"
        f"ORDER BY created_at DESC LIMIT ${limit_idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
