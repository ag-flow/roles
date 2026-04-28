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


async def update_identity(
    role_project_id: UUID,
    identity: str,
    *,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE role_projects SET identity = $2, updated_at = now() WHERE id = $1.

    Lève ValueError si aucune ligne touchée.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE role_projects SET identity = $2, updated_at = now() WHERE id = $1",
            role_project_id,
            identity,
        )
    try:
        rows = int(result.split()[-1])
    except (IndexError, ValueError):
        rows = 0
    if rows == 0:
        raise ValueError(f"role_project {role_project_id} not found")


async def list_for_user(user_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """SELECT * FROM role_projects WHERE user_id=$1 ORDER BY created_at DESC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM role_projects WHERE user_id = $1 ORDER BY created_at DESC",
            user_id,
        )
    return [dict(r) for r in rows]


async def update_mistral_secret_ref(
    role_project_id: UUID,
    secret_ref: str | None,
    *,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE role_projects SET mistral_secret_ref=$2, updated_at=now() WHERE id=$1.

    Lève ValueError si rows=0 (project introuvable).
    secret_ref peut être None pour reset.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE role_projects SET mistral_secret_ref = $2, updated_at = now() WHERE id = $1",
            role_project_id,
            secret_ref,
        )
    try:
        rows = int(result.split()[-1])
    except (IndexError, ValueError):
        rows = 0
    if rows == 0:
        raise ValueError(f"role_project {role_project_id} not found")


async def update_target_role_id(
    role_project_id: UUID,
    target_role_id: str,
    *,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE role_projects SET target_role_id=$2, updated_at=now() WHERE id=$1.

    Lève ValueError si rows=0.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE role_projects SET target_role_id = $2, updated_at = now() WHERE id = $1",
            role_project_id,
            target_role_id,
        )
    try:
        rows = int(result.split()[-1])
    except (IndexError, ValueError):
        rows = 0
    if rows == 0:
        raise ValueError(f"role_project {role_project_id} not found")
