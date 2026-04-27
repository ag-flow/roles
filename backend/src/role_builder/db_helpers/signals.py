"""CRUD asyncpg pour la table ``signals`` (migration 0008).

Les signaux sont les unités atomiques produites par l'étage extractor.
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

_INSERT_SIGNAL_SQL = """
    INSERT INTO signals
        (run_id, role_project_id, tenant_id, source_item_id,
         source_chunks, type, content)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING id
"""

_LIST_BY_RUN_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, source_item_id,
           source_chunks, type, content, created_at
    FROM signals
    WHERE run_id = $1
    ORDER BY created_at ASC
"""

_LIST_BY_PROJECT_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, source_item_id,
           source_chunks, type, content, created_at
    FROM signals
    WHERE role_project_id = $1
    ORDER BY created_at DESC
"""

_LIST_BY_PROJECT_FILTERED_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, source_item_id,
           source_chunks, type, content, created_at
    FROM signals
    WHERE role_project_id = $1 AND type = $2
    ORDER BY created_at DESC
"""

_GET_BY_IDS_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, source_item_id,
           source_chunks, type, content, created_at
    FROM signals
    WHERE id = ANY($1::uuid[])
"""

_DELETE_BY_RUN_SQL = "DELETE FROM signals WHERE run_id = $1"


async def insert_signal(
    *,
    run_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    source_item_id: UUID | None = None,
    source_chunks: list[UUID],
    signal_type: str,
    content: dict,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT un signal et retourne son UUID.

    ``content`` est sérialisé en JSON via json.dumps.
    ``source_chunks`` est passé tel quel (asyncpg gère uuid[] natif).
    """
    content_json = json.dumps(content)
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            _INSERT_SIGNAL_SQL,
            run_id,
            role_project_id,
            tenant_id,
            source_item_id,
            source_chunks,
            signal_type,
            content_json,
        )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def list_signals_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """Retourne les signaux d'un run, triés par created_at ASC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_RUN_SQL, run_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_signals_by_project(
    role_project_id: UUID,
    *,
    type: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict]:
    """Retourne les signaux d'un projet, triés par created_at DESC.

    Si ``type`` est fourni, filtre sur ce type.
    """
    async with pool.acquire() as conn:
        if type is not None:
            rows = await conn.fetch(_LIST_BY_PROJECT_FILTERED_SQL, role_project_id, type)
        else:
            rows = await conn.fetch(_LIST_BY_PROJECT_SQL, role_project_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_signals_by_ids(ids: list[UUID], *, pool: asyncpg.Pool) -> list[dict]:
    """Retourne les signaux par leurs ids.

    Liste vide → retourne [] sans appel SQL.
    """
    if not ids:
        return []
    async with pool.acquire() as conn:
        rows = await conn.fetch(_GET_BY_IDS_SQL, ids)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def delete_signals_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Supprime tous les signals d'un run. Retourne le count supprimé."""
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_RUN_SQL, run_id)
    # asyncpg execute retourne "DELETE N"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
