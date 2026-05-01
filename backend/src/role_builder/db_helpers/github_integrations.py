"""CRUD asyncpg pour la table github_integrations.

Phase 2 sous-projet D : un user peut désormais avoir plusieurs intégrations
(unicité sur le couple ``(user_id, github_user_id)``). ``upsert`` réutilise
ce couple pour rafraîchir une intégration existante ou en créer une nouvelle.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg

_UPSERT_SQL = """
    INSERT INTO github_integrations
        (tenant_id, user_id, github_login, github_user_id,
         openbao_path, scope, last_validated_at)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    ON CONFLICT (user_id, github_user_id) DO UPDATE SET
        tenant_id = EXCLUDED.tenant_id,
        github_login = EXCLUDED.github_login,
        openbao_path = EXCLUDED.openbao_path,
        scope = EXCLUDED.scope,
        last_validated_at = EXCLUDED.last_validated_at
"""

_GET_PRIMARY_BY_USER_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           openbao_path, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
    ORDER BY last_validated_at DESC NULLS LAST, created_at DESC
    LIMIT 1
"""

_LIST_BY_USER_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           openbao_path, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE user_id = $1
    ORDER BY created_at ASC
"""

_GET_BY_ID_SQL = """
    SELECT id, tenant_id, user_id, github_login, github_user_id,
           openbao_path, scope, last_validated_at, created_at
    FROM github_integrations
    WHERE id = $1
"""

_DELETE_BY_USER_SQL = "DELETE FROM github_integrations WHERE user_id = $1"
_DELETE_BY_ID_SQL = "DELETE FROM github_integrations WHERE id = $1"


def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row) if not isinstance(row, dict) else row


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
    """Insert ou refresh d'une intégration ``(user_id, github_user_id)``.

    Si le couple existe : update des champs (login peut changer si rename
    GitHub, scope, openbao_path, etc.). Sinon : insert d'une nouvelle row.
    """
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


async def get_by_user_id(
    user_id: UUID, *, pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Retourne l'intégration "primary" du user (= la plus récente).

    Critère : ``last_validated_at DESC NULLS LAST, created_at DESC``.
    Utilisé par les routes qui n'ont pas reçu d'``integration_id`` explicite.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_PRIMARY_BY_USER_SQL, user_id)
    return _row_to_dict(row) if row is not None else None


async def list_by_user_id(
    user_id: UUID, *, pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """Liste toutes les intégrations GitHub d'un user, triées par ancienneté."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_USER_SQL, user_id)
    return [_row_to_dict(r) for r in rows]


async def get_by_id(
    integration_id: UUID, *, pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """Retourne une intégration par son id, ou None si inexistante."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_BY_ID_SQL, integration_id)
    return _row_to_dict(row) if row is not None else None


async def delete_by_user_id(user_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Supprime TOUTES les intégrations d'un user. Retourne le rowcount."""
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_USER_SQL, user_id)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def delete_by_id(integration_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Supprime une intégration par son id. Retourne le rowcount (0 ou 1)."""
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_ID_SQL, integration_id)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
