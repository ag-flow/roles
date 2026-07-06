"""Helpers DB pour user_wallets (wallets Harpocrate par utilisateur)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_COLUMNS = "id, tenant_id, user_id, label, api_url, status, created_at, updated_at"


async def insert_wallet(
    *,
    tenant_id: UUID,
    user_id: UUID,
    label: str,
    api_token_encrypted: bytes,
    api_url: str,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT INTO user_wallets RETURNING id."""
    query = (
        "INSERT INTO user_wallets "
        "(tenant_id, user_id, label, api_token_encrypted, api_url) "
        "VALUES ($1, $2, $3, $4, $5) "
        "RETURNING id"
    )
    async with pool.acquire() as conn:
        wallet_id = await conn.fetchval(
            query, tenant_id, user_id, label, api_token_encrypted, api_url
        )
    return wallet_id  # type: ignore[return-value]


async def list_wallets(*, user_id: UUID, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Wallets de l'utilisateur, du plus ancien au plus récent (présélection UI).

    Le token chiffré n'est jamais retourné par ce listing.
    """
    query = (
        f"SELECT {_COLUMNS} FROM user_wallets "  # noqa: S608 — colonnes constantes
        "WHERE user_id = $1 "
        "ORDER BY created_at"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id)
    return [dict(r) for r in rows]


async def get_wallet(
    *, wallet_id: UUID, user_id: UUID, pool: asyncpg.Pool
) -> dict[str, Any] | None:
    """Wallet par id, scoping user (token chiffré inclus — usage interne)."""
    query = "SELECT * FROM user_wallets WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, wallet_id, user_id)
    return dict(row) if row is not None else None


async def delete_wallet(*, wallet_id: UUID, user_id: UUID, pool: asyncpg.Pool) -> bool:
    """DELETE scoping user ; False si le wallet n'existait pas."""
    query = "DELETE FROM user_wallets WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        status = await conn.execute(query, wallet_id, user_id)
    return status == "DELETE 1"


async def count_secrets_for_wallet(*, wallet_id: UUID, pool: asyncpg.Pool) -> int:
    """Nombre de secrets référençant ce wallet (garde-fou avant DELETE)."""
    query = "SELECT count(*) FROM user_secrets WHERE wallet_id = $1"
    async with pool.acquire() as conn:
        count = await conn.fetchval(query, wallet_id)
    return int(count or 0)
