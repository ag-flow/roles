"""CRUD asyncpg pour `role_projects` (cf. migration 0002).

Pour Sprint 3, le seul besoin est de résoudre `user_id` depuis un
`role_project_id` (le scraper job ne porte pas user_id directement —
il faut remonter la chaîne source -> role_project -> user_id pour
décider du worker_pool_id de la transcription).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def get_user_id_for_project(role_project_id: UUID, *, pool: asyncpg.Pool) -> UUID | None:
    """Retourne le user_id propriétaire du role_project, ou None si inexistant."""
    query = "SELECT user_id FROM role_projects WHERE id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchval(query, role_project_id)  # type: ignore[no-any-return]


async def get_by_id(role_project_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    """Retourne la ligne complète du role_project, ou None."""
    query = "SELECT * FROM role_projects WHERE id = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, role_project_id)
    return dict(row) if row else None
