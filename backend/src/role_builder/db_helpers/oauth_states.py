"""CRUD asyncpg pour la table oauth_states (CSRF state OAuth, Sprint 8).

Le state est inséré au démarrage du flow OAuth (GET /auth/github/start),
puis consommé atomiquement (DELETE...RETURNING) au callback. ``consume_state``
filtre côté application les states dont l'``expires_at`` est dans le passé
(défense en profondeur — la TTL est aussi appliquée par cleanup périodique).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO oauth_states (state, user_id, tenant_id, provider, expires_at)
    VALUES ($1, $2, $3, $4, $5)
"""

# DELETE ... RETURNING : atomique. Empêche le replay d'un state déjà consommé.
_CONSUME_SQL = """
    DELETE FROM oauth_states
    WHERE state = $1
    RETURNING user_id, tenant_id, expires_at
"""

_CLEANUP_SQL = "DELETE FROM oauth_states WHERE expires_at < now()"


async def insert_state(
    *,
    state: str,
    user_id: UUID,
    tenant_id: UUID,
    ttl_seconds: int = 600,
    provider: str = "github",
    pool: asyncpg.Pool,
) -> None:
    """Stocke un state CSRF avec une TTL de ttl_seconds (défaut 10 min)."""
    expires_at = datetime.now(tz=UTC) + timedelta(seconds=ttl_seconds)
    async with pool.acquire() as conn:
        await conn.execute(_INSERT_SQL, state, user_id, tenant_id, provider, expires_at)


async def consume_state(state: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Récupère et supprime atomiquement un state. Retourne None si absent/expiré."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_CONSUME_SQL, state)
    if row is None:
        return None
    data = dict(row) if not isinstance(row, dict) else row
    expires_at = data.get("expires_at")
    if isinstance(expires_at, datetime) and expires_at < datetime.now(tz=UTC):
        return None
    return data


async def cleanup_expired(*, pool: asyncpg.Pool) -> int:
    """Supprime les states expirés. Retourne le nombre supprimé."""
    async with pool.acquire() as conn:
        result = await conn.execute(_CLEANUP_SQL)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
