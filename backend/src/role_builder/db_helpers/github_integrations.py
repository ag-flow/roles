"""CRUD asyncpg pour la table github_integrations (Sprint 8).

Une seule intégration GitHub par user (UNIQUE constraint sur user_id en DB).
``upsert`` utilise ON CONFLICT (user_id) DO UPDATE — appelé après un succès
OAuth pour créer ou rafraîchir l'intégration.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg

_UPSERT_SQL = """
    INSERT INTO github_integrations
        (tenant_id, user_id, github_login, github_user_id,
         openbao_path, scope, last_validated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (user_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        github_login = EXCLUDED.github_login,
        github_user_id = EXCLUDED.github_user_id,
        openbao_path = EXCLUDED.openbao_path,
        scope = EXCLUDED.scope,
        last_validated_at = EXCLUDED.last_validated_at
"""

_GET_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           openbao_path, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
"""

_DELETE_SQL = "DELETE FROM github_integrations WHERE user_id = $1"


async def upsert(
    *,
    user_id: UUID,
    tenant_id: UUID,
    github_login: str,
    github_user_id: int,
    openbao_path: str,
    scope: str,
    pool: asyncpg.Pool,
) -> None:
    """Insert ou update sur conflit user_id (1 seul GitHub par user)."""
    async with pool.acquire() as conn:
        await conn.execute(
            _UPSERT_SQL,
            tenant_id,
            user_id,
            github_login,
            github_user_id,
            openbao_path,
            scope,
            datetime.now(tz=UTC),
        )


async def get_by_user_id(user_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_SQL, user_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row


async def delete_by_user_id(user_id: UUID, *, pool: asyncpg.Pool) -> int:
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_SQL, user_id)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
