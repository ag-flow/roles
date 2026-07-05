"""Helpers DB pour user_secrets (secrets typés, stockage local ou wallet)."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

# Colonnes sûres pour les listings API : jamais value_encrypted.
_LIST_COLUMNS = (
    "id, tenant_id, user_id, secret_type, label, storage, wallet_id, "
    "wallet_path, status, created_at, updated_at"
)


async def insert_secret(
    *,
    secret_id: UUID,
    tenant_id: UUID,
    user_id: UUID,
    secret_type: str,
    label: str,
    storage: str,
    value_encrypted: bytes | None,
    wallet_id: UUID | None,
    wallet_path: str | None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT INTO user_secrets RETURNING id.

    L'id est fourni par l'appelant : le SecretStore le génère avant l'écriture
    wallet pour que wallet_path contienne l'id définitif.
    """
    query = (
        "INSERT INTO user_secrets "
        "(id, tenant_id, user_id, secret_type, label, storage, "
        "value_encrypted, wallet_id, wallet_path) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) "
        "RETURNING id"
    )
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            query,
            secret_id,
            tenant_id,
            user_id,
            secret_type,
            label,
            storage,
            value_encrypted,
            wallet_id,
            wallet_path,
        )
    return row_id  # type: ignore[return-value]


async def list_secrets(
    *,
    user_id: UUID,
    secret_type: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """Secrets de l'utilisateur, sans les valeurs chiffrées."""
    if secret_type is not None:
        query = (
            f"SELECT {_LIST_COLUMNS} FROM user_secrets "  # noqa: S608
            "WHERE user_id = $1 AND secret_type = $2 "
            "ORDER BY created_at"
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, secret_type)
    else:
        query = (
            f"SELECT {_LIST_COLUMNS} FROM user_secrets "  # noqa: S608
            "WHERE user_id = $1 "
            "ORDER BY created_at"
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
    return [dict(r) for r in rows]


async def get_secret(
    *, secret_id: UUID, user_id: UUID, pool: asyncpg.Pool
) -> dict[str, Any] | None:
    """Secret par id, scoping user (valeur chiffrée incluse — usage interne)."""
    query = "SELECT * FROM user_secrets WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, secret_id, user_id)
    return dict(row) if row is not None else None


async def delete_secret(*, secret_id: UUID, user_id: UUID, pool: asyncpg.Pool) -> bool:
    """DELETE scoping user ; False si le secret n'existait pas."""
    query = "DELETE FROM user_secrets WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        status = await conn.execute(query, secret_id, user_id)
    return status == "DELETE 1"


async def count_service_references(*, secret_id: UUID, pool: asyncpg.Pool) -> int:
    """Nombre de définitions de service référençant ce secret (garde-fou DELETE)."""
    query = (
        "SELECT "
        "(SELECT count(*) FROM user_transcription_keys WHERE secret_id = $1) "
        "+ (SELECT count(*) FROM user_credentials WHERE secret_id = $1)"
    )
    async with pool.acquire() as conn:
        count = await conn.fetchval(query, secret_id)
    return int(count or 0)


async def update_secret_status(
    *, secret_id: UUID, status: str, pool: asyncpg.Pool
) -> None:
    """UPDATE du statut (active/invalid) + updated_at."""
    query = "UPDATE user_secrets SET status = $2, updated_at = now() WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, secret_id, status)
