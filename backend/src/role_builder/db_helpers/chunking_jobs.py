"""CRUD asyncpg pour la table ``chunking_jobs`` (cf. migration 0005).

``claim_next_pending_job`` exécute en une seule transaction :
1. SELECT ... FROM chunking_jobs WHERE status='pending' ... FOR UPDATE SKIP LOCKED
2. UPDATE chunking_jobs SET status='claimed', claimed_by, claimed_at, attempts+1
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO chunking_jobs
        (source_item_id, role_project_id, tenant_id, transcript_s3_key, status)
    VALUES ($1, $2, $3, $4, 'pending')
    RETURNING id
"""

_SELECT_NEXT_SQL = """
    SELECT id, source_item_id, role_project_id, tenant_id,
           transcript_s3_key, attempts
    FROM chunking_jobs
    WHERE status = 'pending'
    ORDER BY created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""

_CLAIM_UPDATE_SQL = """
    UPDATE chunking_jobs
    SET status = 'claimed',
        claimed_by = $1,
        claimed_at = now(),
        attempts = attempts + 1,
        updated_at = now()
    WHERE id = $2
"""

_MARK_PROCESSING_SQL = """
    UPDATE chunking_jobs
    SET status = 'processing', started_at = now(), updated_at = now()
    WHERE id = $1
"""

_MARK_DONE_SQL = """
    UPDATE chunking_jobs
    SET status = 'done',
        chunks_produced = $1,
        completed_at = now(),
        updated_at = now()
    WHERE id = $2
"""

_MARK_FAILED_SQL = """
    UPDATE chunking_jobs
    SET status = 'failed',
        error = $1,
        completed_at = now(),
        updated_at = now()
    WHERE id = $2
"""


async def insert_job(
    *,
    source_item_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    transcript_s3_key: str,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert un chunking_job pending et retourne l'id généré."""
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            _INSERT_SQL,
            source_item_id,
            role_project_id,
            tenant_id,
            transcript_s3_key,
        )
    return new_id  # type: ignore[no-any-return]


async def claim_next_pending_job(worker_id: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Atomically claim le prochain chunking_job pending. None si vide."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(_SELECT_NEXT_SQL)
            if row is None:
                return None
            job = dict(row) if not isinstance(row, dict) else row
            await conn.execute(_CLAIM_UPDATE_SQL, worker_id, job["id"])
    return job


async def mark_processing(job_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Move job to 'processing' (appelé en début de process_one_job)."""
    async with pool.acquire() as conn:
        await conn.execute(_MARK_PROCESSING_SQL, job_id)


async def mark_done(job_id: UUID, *, chunks_produced: int, pool: asyncpg.Pool) -> None:
    """Move job to 'done' avec compteur chunks_produced."""
    async with pool.acquire() as conn:
        await conn.execute(_MARK_DONE_SQL, chunks_produced, job_id)


async def mark_failed(job_id: UUID, error: str, *, pool: asyncpg.Pool) -> None:
    """Move job to 'failed' avec error message + completed_at."""
    async with pool.acquire() as conn:
        await conn.execute(_MARK_FAILED_SQL, error, job_id)


async def list_jobs(
    *,
    status: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List chunking_jobs newest-first, optional status filter."""
    params: list[Any] = []
    where = ""
    if status is not None:
        params.append(status)
        where = "WHERE status = $1 "
    params.append(limit)
    limit_idx = len(params)
    query = (
        "SELECT id, source_item_id, role_project_id, tenant_id, "
        "transcript_s3_key, status, attempts, error, chunks_produced, "
        "created_at, started_at, completed_at "
        "FROM chunking_jobs "
        f"{where}"
        f"ORDER BY created_at DESC LIMIT ${limit_idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


_ENQUEUE_FOR_PROJECT_SQL = """
    INSERT INTO chunking_jobs
        (source_item_id, role_project_id, tenant_id, transcript_s3_key, status)
    SELECT si.id, $1, si.tenant_id, si.transcript_s3_key, 'pending'
    FROM source_items si
    JOIN sources s ON s.id = si.source_id
    WHERE s.role_project_id = $1
      AND si.transcript_s3_key IS NOT NULL
"""


async def enqueue_for_project(
    role_project_id: UUID, *, pool: asyncpg.Pool,
) -> int:
    """Enqueue un chunking_job pending pour chaque source_item du projet
    qui a un transcript. Retourne le rowcount inséré.

    Phase 2 sous-projet E : utilisé par le rebuild corpus.
    """
    async with pool.acquire() as conn:
        tag = await conn.execute(_ENQUEUE_FOR_PROJECT_SQL, role_project_id)
    try:
        return int(tag.split()[-1])
    except (IndexError, ValueError):
        return 0
