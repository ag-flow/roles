"""CRUD asyncpg pour `acquisition_requests` (cf. migration 0005).

`insert_request` propage `asyncpg.UniqueViolationError` sur collision de
`request_key` : le retry (nouveau suffixe) est de la responsabilité du
service appelant (cf. `services.acquisition.request_key`).
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

_INSERT_SQL = """
    INSERT INTO acquisition_requests
        (request_key, tenant_id, submitted_by, kind, source_id, mode,
         filters, docflow_target, note, status)
    VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10)
    RETURNING id
"""


async def insert_request(
    *,
    request_key: str,
    tenant_id: UUID,
    submitted_by: str,
    kind: str,
    source_id: UUID | None,
    mode: str | None,
    filters: dict[str, Any] | None,
    docflow_target: dict[str, Any] | None,
    note: str | None,
    status: str,
    pool: asyncpg.Pool,
) -> UUID:
    """Insert une acquisition_request et retourne son id."""
    async with pool.acquire() as conn:
        new_id = await conn.fetchval(
            _INSERT_SQL,
            request_key,
            tenant_id,
            submitted_by,
            kind,
            source_id,
            mode,
            json.dumps(filters) if filters is not None else None,
            json.dumps(docflow_target) if docflow_target is not None else None,
            note,
            status,
        )
    return new_id  # type: ignore[no-any-return]


async def get_by_key(request_key: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Fetch une acquisition_request par sa request_key ; None si absente."""
    query = "SELECT * FROM acquisition_requests WHERE request_key = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, request_key)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def get_by_source_id(source_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Fetch l'acquisition_request rattachée à une source ; None si absente.

    Utilisé par event_handlers pour retrouver la requête d'origine d'un
    source_id lors du traitement des events scraper (branche la couche
    requête sur le pipeline existant sans le réécrire).
    """
    query = "SELECT * FROM acquisition_requests WHERE source_id = $1"
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query, source_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def update_status(request_key: str, status: str, *, pool: asyncpg.Pool) -> None:
    """Update le statut d'une requête (updated_at touché)."""
    query = """
        UPDATE acquisition_requests
        SET status = $1, updated_at = now()
        WHERE request_key = $2
    """
    async with pool.acquire() as conn:
        await conn.execute(query, status, request_key)


async def list_requests(
    *,
    status: str | None = None,
    submitted_by: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List acquisition_requests newest-first, filtres optionnels status + submitted_by."""
    clauses: list[str] = []
    params: list[Any] = []

    if status is not None:
        params.append(status)
        clauses.append(f"status = ${len(params)}")
    if submitted_by is not None:
        params.append(submitted_by)
        clauses.append(f"submitted_by = ${len(params)}")

    params.append(limit)
    limit_idx = len(params)

    where = ""
    if clauses:
        where = "WHERE " + " AND ".join(clauses) + " "

    query = (
        "SELECT * FROM acquisition_requests "
        f"{where}"
        f"ORDER BY created_at DESC LIMIT ${limit_idx}"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
