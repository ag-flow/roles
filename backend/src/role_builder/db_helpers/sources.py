"""CRUD asyncpg pour la table `sources` (cf. migration 0003)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def insert_source(
    *,
    tenant_id: UUID,
    platform: str,
    source_type: str,
    url: str,
    credentials_id: UUID | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert a new row into `sources`. Status defaults to 'pending_discovery'.

    En V2 une source est rattachée à une `acquisition_request` (façade MCP),
    plus à un role_project (concept retiré, migration 0011).
    """
    query = """
        INSERT INTO sources
            (tenant_id, platform, source_type, url, credentials_id)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING id
    """
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            query, tenant_id, platform, source_type, url, credentials_id
        )
    return new_id  # type: ignore[no-any-return]


async def update_source_status(
    source_id: UUID,
    status: str,
    *,
    discovered_count: int | None = None,
    error: str | None = None,
    pool: asyncpg.Pool,
) -> None:
    """Update status (+ optional discovered_count / error). Touches updated_at via trigger."""
    query = """
        UPDATE sources
        SET status = $1,
            discovered_count = COALESCE($2, discovered_count),
            error = COALESCE($3, error),
            updated_at = now()
        WHERE id = $4
    """
    async with pool.acquire() as conn:
        await conn.execute(query, status, discovered_count, error, source_id)


async def get_source(source_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Fetch a single source by id; returns dict-like row or None."""
    query = "SELECT * FROM sources WHERE id = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, source_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row
