"""CRUD asyncpg pour role_publications (Sprint 8 — historique publications GitHub)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO role_publications
        (role_project_id, tenant_id, user_id, commit_sha, files_count, summary)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id, published_at
"""

_LIST_SQL = """
    SELECT id, role_project_id, tenant_id, user_id, commit_sha,
           published_at, files_count, summary
    FROM role_publications
    WHERE role_project_id = $1
    ORDER BY published_at DESC
    LIMIT $2
"""

_LATEST_SQL = """
    SELECT published_at, commit_sha
    FROM role_publications
    WHERE role_project_id = $1
    ORDER BY published_at DESC
    LIMIT 1
"""


async def insert(
    *,
    role_project_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    commit_sha: str,
    files_count: int,
    summary: str,
    pool: asyncpg.Pool,
) -> dict[str, Any]:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            _INSERT_SQL,
            role_project_id,
            tenant_id,
            user_id,
            commit_sha,
            files_count,
            summary,
        )
    return dict(row) if not isinstance(row, dict) else row


async def list_by_project(
    project_id: UUID,
    *,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_SQL, project_id, limit)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_latest(project_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_LATEST_SQL, project_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row
