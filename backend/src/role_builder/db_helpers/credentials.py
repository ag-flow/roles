"""Helpers DB pour user_credentials (insert, list, get, update_status, revoke, delete)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from role_builder.config import settings


def get_cookies_b64(platform: str) -> str:
    """Return the platform-specific cookies B64 from Settings.

    Empty string for unknown platform or unset cookie. Lookup is
    case-insensitive on the platform name.
    """
    key = platform.lower()
    if key == "youtube":
        return settings.youtube_cookies_b64
    if key == "instagram":
        return settings.instagram_cookies_b64
    if key == "tiktok":
        return settings.tiktok_cookies_b64
    return ""


async def insert_user_credential(
    *,
    tenant_id: UUID,
    user_id: UUID,
    platform: str,
    label: str | None,
    vault_secret_name: str,
    status: str = "active",
    last_validated_at: datetime | None = None,
    expires_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT INTO user_credentials RETURNING id."""
    query = (
        "INSERT INTO user_credentials "
        "(tenant_id, user_id, platform, label, vault_secret_name, status, "
        "last_validated_at, expires_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8) "
        "RETURNING id"
    )
    async with pool.acquire() as conn:
        row_id = await conn.fetchval(
            query,
            tenant_id,
            user_id,
            platform,
            label,
            vault_secret_name,
            status,
            last_validated_at,
            expires_at,
        )
    return row_id  # type: ignore[return-value]


async def list_credentials(
    *,
    user_id: UUID,
    platform: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """SELECT user_credentials WHERE user_id=$1 [AND platform=$2] ORDER BY created_at DESC."""
    if platform is not None:
        query = (
            "SELECT * FROM user_credentials "
            "WHERE user_id = $1 AND platform = $2 "
            "ORDER BY created_at DESC"
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, user_id, platform)
    else:
        query = "SELECT * FROM user_credentials WHERE user_id = $1 ORDER BY created_at DESC"
        async with pool.acquire() as conn:
            rows = await conn.fetch(query, user_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_credential(
    cred_id: UUID,
    *,
    user_id: UUID,
    pool: asyncpg.Pool,
) -> dict[str, Any] | None:
    """SELECT WHERE id=$1 AND user_id=$2 (sécurité multi-user)."""
    query = "SELECT * FROM user_credentials WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, cred_id, user_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def update_credential_status(
    cred_id: UUID,
    *,
    status: str,
    last_validated_at: datetime | None = None,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE status (et last_validated_at si fourni), updated_at=now() WHERE id=$1."""
    if last_validated_at is not None:
        query = (
            "UPDATE user_credentials "
            "SET status = $2, last_validated_at = $3, updated_at = now() "
            "WHERE id = $1"
        )
        async with pool.acquire() as conn:
            await conn.execute(query, cred_id, status, last_validated_at)
    else:
        query = "UPDATE user_credentials SET status = $2, updated_at = now() WHERE id = $1"
        async with pool.acquire() as conn:
            await conn.execute(query, cred_id, status)


async def revoke_credential(cred_id: UUID, *, pool: asyncpg.Pool) -> None:
    """UPDATE status='revoked', updated_at=now() WHERE id=$1."""
    query = "UPDATE user_credentials SET status = 'revoked', updated_at = now() WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, cred_id)


async def delete_credential(cred_id: UUID, *, pool: asyncpg.Pool) -> None:
    """DELETE FROM user_credentials WHERE id=$1."""
    query = "DELETE FROM user_credentials WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, cred_id)
