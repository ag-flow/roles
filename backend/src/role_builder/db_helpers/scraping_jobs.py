"""CRUD asyncpg pour la table `scraping_jobs` (cf. migration 0005).

`claim_next_pending_job` exécute en une seule transaction :
1. SELECT ... FROM scraping_jobs WHERE status='pending' ... FOR UPDATE SKIP LOCKED
2. UPDATE scraping_jobs SET status='claimed', claimed_by, claimed_at, attempts+1
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_SELECT_NEXT_SQL = """
    SELECT id, source_id, source_item_id, tenant_id, credentials_id,
           command, priority, attempts
    FROM scraping_jobs
    WHERE status = 'pending'
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""

_CLAIM_UPDATE_SQL = """
    UPDATE scraping_jobs
    SET status = 'claimed',
        claimed_by = $1,
        claimed_at = now(),
        attempts = attempts + 1,
        updated_at = now()
    WHERE id = $2
"""


async def insert_job(
    *,
    source_id: UUID,
    source_item_id: UUID | None,
    tenant_id: UUID,
    command: str,
    credentials_id: UUID | None = None,
    priority: int = 0,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert a scraping job. Status defaults to 'pending'."""
    query = """
        INSERT INTO scraping_jobs
            (source_id, source_item_id, tenant_id, credentials_id,
             command, status, priority)
        VALUES ($1, $2, $3, $4, $5, 'pending', $6)
        RETURNING id
    """
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            query, source_id, source_item_id, tenant_id, credentials_id, command, priority
        )
    return new_id  # type: ignore[no-any-return]


async def claim_next_pending_job(worker_id: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Atomically claim the highest-priority pending job and return its row.

    Returns None when no pending job is available.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(_SELECT_NEXT_SQL)
            if row is None:
                return None
            job = dict(row) if not isinstance(row, dict) else row
            await conn.execute(_CLAIM_UPDATE_SQL, worker_id, job["id"])
    return job


async def mark_job_processing(job_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Move job to 'processing' status (called when container is about to be launched)."""
    query = """
        UPDATE scraping_jobs
        SET status = 'processing', started_at = now(), updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(query, job_id)


async def mark_job_done(job_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Move job to 'done' status with completed_at."""
    query = """
        UPDATE scraping_jobs
        SET status = 'done', completed_at = now(), updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(query, job_id)


async def mark_job_failed(job_id: UUID, error: str, *, pool: asyncpg.Pool) -> None:
    """Move job to 'failed' with error message and completed_at."""
    query = """
        UPDATE scraping_jobs
        SET status = 'failed', error = $1, completed_at = now(), updated_at = now()
        WHERE id = $2
    """
    async with pool.acquire() as conn:
        await conn.execute(query, error, job_id)


async def get_active_job_for_item(
    source_item_id: UUID, command: str, *, pool: asyncpg.Pool
) -> bool:
    """True si un job pending/claimed/processing existe déjà pour cet item+command.

    Utilisé par roles__select_items pour rester idempotent : une sélection
    répétée ne doit pas ré-enqueuer un download déjà en vol.
    """
    query = """
        SELECT 1 FROM scraping_jobs
        WHERE source_item_id = $1 AND command = $2
          AND status IN ('pending', 'claimed', 'processing')
        LIMIT 1
    """
    async with pool.acquire() as conn:
        row = await conn.fetchval(query, source_item_id, command)
    return row is not None


async def cancel_pending_claimed(source_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Annule (status='cancelled') les jobs pending/claimed d'une source.

    Retourne le nombre de lignes modifiées. Les jobs déjà 'processing' ne
    sont pas touchés (cf. roles__cancel_request §2.5 : "jobs pending").
    """
    query = """
        UPDATE scraping_jobs
        SET status = 'cancelled', updated_at = now()
        WHERE source_id = $1 AND status IN ('pending', 'claimed')
    """
    async with pool.acquire() as conn:
        result = await conn.execute(query, source_id)
    return _parse_update_count(result)


def _parse_update_count(execute_result: str) -> int:
    parts = execute_result.split()
    if len(parts) >= 2 and parts[0].upper() == "UPDATE":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0


async def list_jobs(
    *,
    status: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List scraping_jobs newest-first, optionally filtered by status."""
    params: list[Any] = []
    where = ""
    if status is not None:
        params.append(status)
        where = "WHERE status = $1 "
    params.append(limit)
    limit_idx = len(params)
    query = (
        "SELECT id, source_id, source_item_id, tenant_id, command, status, "
        "priority, attempts, error, created_at, started_at, completed_at "
        "FROM scraping_jobs "
        f"{where}"
        f"ORDER BY created_at DESC LIMIT ${limit_idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
