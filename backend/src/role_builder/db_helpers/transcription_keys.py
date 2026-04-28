"""CRUD asyncpg pour `user_transcription_keys` (cf. migration 0006).

Helpers Sprint 3 :
- Listing des clés actives (globalement ou par user)
- Récupération de la primary key d'un user (is_primary=true AND status='active')
- mark_exhausted / mark_invalid lors d'erreurs provider (HTTP 402, 401, etc.)

Sprint 6 :
- CRUD complet (insert, list_keys_for_user, get_key, update_key_settings,
  update_key_balance, increment_spend, reset_monthly_spend_all,
  revoke_key, delete_key, list_active_keys_for_balance_polling)
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


async def list_active_keys(*, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Liste toutes les clés transcription dont status='active' (global)."""
    query = "SELECT * FROM user_transcription_keys WHERE status = 'active' ORDER BY created_at ASC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_active_keys_for_user(user_id: UUID, *, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Liste les clés actives d'un user particulier (toutes providers)."""
    query = (
        "SELECT * FROM user_transcription_keys "
        "WHERE user_id = $1 AND status = 'active' "
        "ORDER BY created_at ASC"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_primary_key(user_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
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
        "UPDATE user_transcription_keys SET status = 'exhausted', updated_at = now() WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)


async def mark_invalid(key_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Bascule status='invalid' (clé révoquée / unauthorized côté provider)."""
    query = (
        "UPDATE user_transcription_keys SET status = 'invalid', updated_at = now() WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)


# ---------------------------------------------------------------------------
# Sprint 6 — CRUD complet
# ---------------------------------------------------------------------------


async def insert_transcription_key(
    *,
    tenant_id: UUID,
    user_id: UUID,
    provider: str,
    label: str | None,
    openbao_path: str,
    workers_count: int = 1,
    is_primary: bool = False,
    is_fallback: bool = False,
    monthly_cap_usd: float | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT INTO user_transcription_keys RETURNING id.

    Si is_primary=True : transaction qui démote d'abord les autres primary
    du même user, puis insère la nouvelle ligne avec is_primary=true.
    """
    insert_query = (
        "INSERT INTO user_transcription_keys "
        "(tenant_id, user_id, provider, label, openbao_path, workers_count, "
        "is_primary, is_fallback, monthly_cap_usd, status, last_validated_at) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'active', now()) "
        "RETURNING id"
    )
    demote_query = (
        "UPDATE user_transcription_keys "
        "SET is_primary = false, updated_at = now() "
        "WHERE user_id = $1 AND is_primary = true"
    )
    async with pool.acquire() as conn:
        if is_primary:
            async with conn.transaction():
                await conn.execute(demote_query, user_id)
                row_id = await conn.fetchval(
                    insert_query,
                    tenant_id,
                    user_id,
                    provider,
                    label,
                    openbao_path,
                    workers_count,
                    is_primary,
                    is_fallback,
                    monthly_cap_usd,
                )
        else:
            row_id = await conn.fetchval(
                insert_query,
                tenant_id,
                user_id,
                provider,
                label,
                openbao_path,
                workers_count,
                is_primary,
                is_fallback,
                monthly_cap_usd,
            )
    return row_id  # type: ignore[return-value]


async def list_keys_for_user(user_id: UUID, *, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """SELECT * WHERE user_id=$1 ORDER BY created_at DESC. Tous status."""
    query = "SELECT * FROM user_transcription_keys WHERE user_id = $1 ORDER BY created_at DESC"
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, user_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_key(key_id: UUID, *, user_id: UUID, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """SELECT * WHERE id=$1 AND user_id=$2."""
    query = "SELECT * FROM user_transcription_keys WHERE id = $1 AND user_id = $2"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, key_id, user_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def update_key_settings(
    key_id: UUID,
    *,
    workers_count: int | None = None,
    is_primary: bool | None = None,
    is_fallback: bool | None = None,
    monthly_cap_usd: float | None = None,
    pool: asyncpg.Pool,
) -> None:
    """Build dynamic SET clause selon les non-None.

    Si is_primary=True : transaction qui démote les autres avant.
    updated_at=now() systématiquement.
    Si tous params None : no-op (pas d'appel SQL).
    """
    parts: list[str] = []
    values: list[Any] = []
    idx = 2  # $1 est key_id

    if workers_count is not None:
        parts.append(f"workers_count = ${idx}")
        values.append(workers_count)
        idx += 1
    if is_primary is not None:
        parts.append(f"is_primary = ${idx}")
        values.append(is_primary)
        idx += 1
    if is_fallback is not None:
        parts.append(f"is_fallback = ${idx}")
        values.append(is_fallback)
        idx += 1
    if monthly_cap_usd is not None:
        parts.append(f"monthly_cap_usd = ${idx}")
        values.append(monthly_cap_usd)
        idx += 1

    if not parts:
        return  # no-op

    parts.append("updated_at = now()")
    set_clause = ", ".join(parts)
    update_query = f"UPDATE user_transcription_keys SET {set_clause} WHERE id = $1"

    async with pool.acquire() as conn:
        if is_primary is True:
            # Récupère user_id de la clé pour démote les autres
            user_row = await conn.fetchrow(
                "SELECT user_id FROM user_transcription_keys WHERE id = $1", key_id
            )
            async with conn.transaction():
                if user_row is not None:
                    await conn.execute(
                        "UPDATE user_transcription_keys "
                        "SET is_primary = false, updated_at = now() "
                        "WHERE user_id = $1 AND is_primary = true AND id != $2",
                        user_row["user_id"],
                        key_id,
                    )
                await conn.execute(update_query, key_id, *values)
        else:
            await conn.execute(update_query, key_id, *values)


async def update_key_balance(
    key_id: UUID,
    *,
    balance_usd: float | None,
    checked_at: datetime,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE current_balance_usd, last_balance_check_at, updated_at WHERE id=$1."""
    query = (
        "UPDATE user_transcription_keys "
        "SET current_balance_usd = $2, last_balance_check_at = $3, updated_at = now() "
        "WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id, balance_usd, checked_at)


async def increment_spend(key_id: UUID, amount_usd: float, *, pool: asyncpg.Pool) -> float:
    """UPDATE current_month_spend_usd += amount RETURNING new total."""
    query = (
        "UPDATE user_transcription_keys "
        "SET current_month_spend_usd = current_month_spend_usd + $2, updated_at = now() "
        "WHERE id = $1 "
        "RETURNING current_month_spend_usd"
    )
    async with pool.acquire() as conn:
        result = await conn.fetchval(query, key_id, amount_usd)
    return float(result)  # type: ignore[arg-type]


async def reset_monthly_spend_all(*, pool: asyncpg.Pool) -> int:
    """UPDATE SET current_month_spend_usd=0 WHERE current_month_spend_usd > 0.

    Retourne le nombre de lignes touchées.
    """
    query = (
        "UPDATE user_transcription_keys "
        "SET current_month_spend_usd = 0, updated_at = now() "
        "WHERE current_month_spend_usd > 0"
    )
    async with pool.acquire() as conn:
        result = await conn.execute(query)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0


async def revoke_key(key_id: UUID, *, pool: asyncpg.Pool) -> None:
    """UPDATE status='revoked', is_primary=false, is_fallback=false, updated_at=now()."""
    query = (
        "UPDATE user_transcription_keys "
        "SET status = 'revoked', is_primary = false, is_fallback = false, "
        "updated_at = now() "
        "WHERE id = $1"
    )
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)


async def delete_key(key_id: UUID, *, pool: asyncpg.Pool) -> None:
    """DELETE FROM user_transcription_keys WHERE id=$1."""
    query = "DELETE FROM user_transcription_keys WHERE id = $1"
    async with pool.acquire() as conn:
        await conn.execute(query, key_id)


async def list_active_keys_for_balance_polling(*, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """SELECT active keys pour les providers avec balance API (Deepgram MVP)."""
    query = (
        "SELECT * FROM user_transcription_keys "
        "WHERE status = 'active' AND provider IN ('deepgram') "
        "ORDER BY created_at ASC"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
