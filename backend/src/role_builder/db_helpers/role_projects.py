"""CRUD asyncpg pour `role_projects` (cf. migration 0002).

Deux usages restants après la purge V2 (synthèse/export/publication
retirés, cf. docs/specs/OBSOLETE.md) :
- résoudre `user_id` depuis un `role_project_id` (le scraper job ne porte
  pas user_id directement — il faut remonter la chaîne
  source -> role_project -> user_id pour décider du worker_pool_id) ;
- lister les projets d'un user (page d'accueil du frontend).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg


async def get_user_id_for_project(role_project_id: UUID, *, pool: asyncpg.Pool) -> UUID | None:
    """Retourne le user_id propriétaire du role_project, ou None si inexistant."""
    query = "SELECT user_id FROM role_projects WHERE id = $1"
    async with pool.acquire() as conn:
        return await conn.fetchval(query, role_project_id)  # type: ignore[no-any-return]


async def list_for_user(user_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """SELECT * FROM role_projects WHERE user_id=$1 ORDER BY created_at DESC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM role_projects WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    return [dict(r) for r in rows]
