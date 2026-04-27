"""CRUD asyncpg pour `user_transcription_keys` (cf. migration 0006).

Helpers Sprint 3 :
- Listing des clés actives (globalement ou par user)
- Récupération de la primary key d'un user (is_primary=true AND status='active')
- mark_exhausted / mark_invalid lors d'erreurs provider (HTTP 402, 401, etc.)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def list_active_keys(*, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Liste toutes les clés transcription dont status='active' (global)."""
    query = (
        "SELECT * FROM user_transcription_keys "
        "WHERE status = 'active' "
        "ORDER BY created_at ASC"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_active_keys_for_user(
    user_id: UUID, *, pool: asyncpg.Pool
) -> list[dict[str, Any]]:
    """Liste les clés actives d'un user particulier (toutes providers)."""
    query = (
        "SELECT * FROM user_transcription_keys "
        "WHERE user_id = $1 AND status = 'active' "
        "ORDER BY created_at ASC"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_primary_key(
    user_id: UUID, *, pool: asyncpg.Pool
) -> dict[str, Any] | None:
    """Retourne la primary key active d'un user, ou None."""
    query = (
        "SELECT * FROM user_transcription_keys "
        "WHERE user_id = $1 AND is_primary = true AND status = 'active' "
        "LIMIT 1"
    )
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, user_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def mark_exhausted(key_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Bascule status='exhausted' (crédit/quota épuisé côté provider)."""
    query = (
        "UPDATE user_transcription_keys "
        "SET status = 'exhausted', updated_at = now() "
        "WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)


async def mark_invalid(key_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Bascule status='invalid' (clé révoquée / unauthorized côté provider)."""
    query = (
        "UPDATE user_transcription_keys "
        "SET status = 'invalid', updated_at = now() "
        "WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)
