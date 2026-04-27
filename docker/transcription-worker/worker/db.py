"""Helpers asyncpg du worker de transcription.

Lifecycle d'un job (cf. spec 04 § Process d'un job) :
1. claim_next_job → SELECT FOR UPDATE SKIP LOCKED + UPDATE status='claimed' (atomique)
2. mark_job_done(provider_used, costs, result_s3_key)
3. mark_job_failed(error, error_history_entry) : append jsonb + attempts+1
4. update_source_item_to_transcribed après succès

Workers : register_worker (idempotent ON CONFLICT) + update_worker_status.
Bascule : reassign_pending_to_shared sur épuisement de clé.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

# ─── Jobs ────────────────────────────────────────────────────────────────────

_SELECT_NEXT_JOB_SQL = """
    SELECT id, source_item_id, audio_s3_key, language,
           worker_pool_id, attempts
    FROM transcription_jobs
    WHERE status = 'pending'
      AND worker_pool_id = $1
    ORDER BY priority DESC, created_at ASC
    FOR UPDATE SKIP LOCKED
    LIMIT 1
"""

_CLAIM_JOB_SQL = """
    UPDATE transcription_jobs
    SET status = 'claimed',
        claimed_by = $1,
        claimed_at = now(),
        attempts = attempts + 1,
        updated_at = now()
    WHERE id = $2
"""


async def claim_next_job(
    worker_pool_id: str,
    worker_id: str,
    *,
    pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Claim atomiquement le prochain job pending du pool, return None si vide."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(_SELECT_NEXT_JOB_SQL, worker_pool_id)
            if row is None:
                return None
            job = dict(row) if not isinstance(row, dict) else row
            await conn.execute(_CLAIM_JOB_SQL, worker_id, job["id"])
    return job


_MARK_JOB_DONE_SQL = """
    UPDATE transcription_jobs
    SET status = 'done',
        provider_used = $1,
        cost_estimate_usd = $2,
        cost_actual_usd = $3,
        result_s3_key = $4,
        completed_at = now(),
        updated_at = now()
    WHERE id = $5
"""


async def mark_job_done(
    job_id: UUID,
    *,
    provider_used: str,
    cost_estimate_usd: float,
    cost_actual_usd: float | None,
    result_s3_key: str,
    pool: asyncpg.Pool,
) -> None:
    """Marque le job comme done et persiste provider + costs + s3_key résultat."""
    async with pool.acquire() as conn:
        await conn.execute(
            _MARK_JOB_DONE_SQL,
            provider_used,
            cost_estimate_usd,
            cost_actual_usd,
            result_s3_key,
            job_id,
        )


_MARK_JOB_FAILED_SQL = """
    UPDATE transcription_jobs
    SET status = 'failed',
        error = $1,
        error_history = COALESCE(error_history, '[]'::jsonb) || $2::jsonb,
        attempts = attempts + 1,
        completed_at = now(),
        updated_at = now()
    WHERE id = $3
"""


async def mark_job_failed(
    job_id: UUID,
    *,
    error: str,
    error_history_entry: dict[str, Any],
    pool: asyncpg.Pool,
) -> None:
    """Append à error_history, incrémente attempts et set status='failed'."""
    payload = json.dumps(error_history_entry)
    async with pool.acquire() as conn:
        await conn.execute(_MARK_JOB_FAILED_SQL, error, payload, job_id)


_UPDATE_SOURCE_ITEM_SQL = """
    UPDATE source_items
    SET status = 'transcribed',
        transcript_s3_key = $1,
        updated_at = now()
    WHERE id = $2
"""


async def update_source_item_to_transcribed(
    source_item_id: UUID,
    transcript_s3_key: str,
    *,
    pool: asyncpg.Pool,
) -> None:
    """Marque le source_item comme transcribed et stocke le s3_key du transcript."""
    async with pool.acquire() as conn:
        await conn.execute(_UPDATE_SOURCE_ITEM_SQL, transcript_s3_key, source_item_id)


_REASSIGN_PENDING_SQL = """
    WITH updated AS (
        UPDATE transcription_jobs
        SET worker_pool_id = 'shared_default',
            updated_at = now()
        WHERE worker_pool_id = $1
          AND status = 'pending'
        RETURNING id
    )
    SELECT count(*) FROM updated
"""


async def reassign_pending_to_shared(
    user_pool_id: str,
    *,
    pool: asyncpg.Pool,
) -> int:
    """Bascule les jobs pending d'un pool user vers shared_default. Return le count."""
    async with pool.acquire() as conn:
        count = await conn.fetchval(_REASSIGN_PENDING_SQL, user_pool_id)
    return int(count or 0)


# ─── Chunking handoff (Sprint 4) ────────────────────────────────────────────

_INSERT_CHUNKING_JOB_SQL = """
    INSERT INTO chunking_jobs
        (source_item_id, role_project_id, tenant_id, transcript_s3_key, status)
    VALUES ($1, $2, $3, $4, 'pending')
    RETURNING id
"""


_LOOKUP_PROJECT_FROM_ITEM_SQL = """
    SELECT s.role_project_id AS role_project_id, si.tenant_id AS tenant_id
    FROM source_items si
    JOIN sources s ON s.id = si.source_id
    WHERE si.id = $1
"""


async def lookup_role_project_for_item(
    source_item_id: UUID, *, pool: asyncpg.Pool
) -> dict[str, Any] | None:
    """Récupère (role_project_id, tenant_id) à partir d'un source_item_id."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LOOKUP_PROJECT_FROM_ITEM_SQL, source_item_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def insert_chunking_job(
    *,
    source_item_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    transcript_s3_key: str,
    pool: asyncpg.Pool,
) -> UUID:
    """Crée un chunking_job après que le transcript a été uploadé (Sprint 4)."""
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            _INSERT_CHUNKING_JOB_SQL,
            source_item_id,
            role_project_id,
            tenant_id,
            transcript_s3_key,
        )
    return new_id  # type: ignore[no-any-return]


# ─── Workers ─────────────────────────────────────────────────────────────────

_REGISTER_WORKER_SQL = """
    INSERT INTO transcription_workers
        (worker_id, worker_pool_id, provider, status, host, started_at)
    VALUES ($1, $2, $3, $4, $5, now())
    ON CONFLICT (worker_id) DO UPDATE
    SET worker_pool_id = EXCLUDED.worker_pool_id,
        provider = EXCLUDED.provider,
        status = EXCLUDED.status,
        host = EXCLUDED.host,
        started_at = now(),
        stopped_at = NULL
"""


async def register_worker(
    worker_id: str,
    worker_pool_id: str,
    provider: str,
    *,
    status: str,
    host: str | None,
    pool: asyncpg.Pool,
) -> None:
    """Idempotent : INSERT ... ON CONFLICT pour gérer les redémarrages."""
    async with pool.acquire() as conn:
        await conn.execute(
            _REGISTER_WORKER_SQL, worker_id, worker_pool_id, provider, status, host
        )


async def update_worker_status(
    worker_id: str,
    status: str,
    *,
    last_activity_at: datetime | None = None,
    stopped_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> None:
    """SET status + last_activity_at / stopped_at quand fournis."""
    sets = ["status = $1"]
    args: list[Any] = [status]
    if last_activity_at is not None:
        args.append(last_activity_at)
        sets.append(f"last_activity_at = ${len(args)}")
    if stopped_at is not None:
        args.append(stopped_at)
        sets.append(f"stopped_at = ${len(args)}")
    args.append(worker_id)
    query = (
        "UPDATE transcription_workers SET "
        + ", ".join(sets)
        + f" WHERE worker_id = ${len(args)}"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, *args)
