"""Queue de dépôt docflow — `source_items` comme queue (spec v2/01 §3).

Pas de table de jobs dédiée pour l'étape `depositing → deposited` :
`status='transcribed'` = pending, claim atomique par FOR UPDATE SKIP LOCKED
(même pattern que les autres queues, cf. docs/specs/01-data-model.md §9).
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

DOCFLOW_DEPOSIT_FAILED = "DOCFLOW_DEPOSIT_FAILED"


async def claim_next_for_deposit(*, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Claim FIFO le prochain item `transcribed` → `depositing` ; None si vide."""
    query = """
        UPDATE source_items
        SET status = 'depositing', updated_at = now()
        WHERE id = (
            SELECT id FROM source_items
            WHERE status = 'transcribed'
            ORDER BY updated_at ASC
            FOR UPDATE SKIP LOCKED
            LIMIT 1
        )
        RETURNING *
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(query)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def mark_deposited(
    item_id: UUID, *, doc_id: str, slug: str, pool: asyncpg.Pool
) -> None:
    """Passe un item `depositing` → `deposited` avec ses refs docflow."""
    query = """
        UPDATE source_items
        SET status = 'deposited', docflow_doc_id = $1, docflow_slug = $2,
            deposited_at = now(), error = NULL, updated_at = now()
        WHERE id = $3
    """
    async with pool.acquire() as conn:
        await conn.execute(query, doc_id, slug, item_id)


async def mark_deposit_failed(item_id: UUID, *, message: str, pool: asyncpg.Pool) -> None:
    """Passe un item en `failed` avec `error.code=DOCFLOW_DEPOSIT_FAILED`.

    Ne touche pas `transcript_s3_key` : le transcript reste dans MinIO pour
    `roles__retry_failed` (spec v2/01 §3, critère §6 ligne 7).
    """
    error = json.dumps({"code": DOCFLOW_DEPOSIT_FAILED, "message": message}, ensure_ascii=False)
    query = """
        UPDATE source_items
        SET status = 'failed', error = $1, updated_at = now()
        WHERE id = $2
    """
    async with pool.acquire() as conn:
        await conn.execute(query, error, item_id)


async def reset_failed_deposit(item_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Remet un item `failed` au dépôt en `transcribed` (roles__retry_failed).

    Le transcript est toujours dans MinIO : pas de re-download ni de
    re-transcription, le worker de dépôt reprend l'item tel quel.
    """
    query = """
        UPDATE source_items
        SET status = 'transcribed', error = NULL, updated_at = now()
        WHERE id = $1
    """
    async with pool.acquire() as conn:
        await conn.execute(query, item_id)


async def requeue_stale_depositing(*, pool: asyncpg.Pool) -> int:
    """Remet les items `depositing` orphelins en `transcribed` (reprise crash).

    À appeler au démarrage de la boucle de dépôt uniquement : suppose un seul
    worker de dépôt par déploiement (même hypothèse que l'orchestrator).
    """
    query = """
        UPDATE source_items
        SET status = 'transcribed', updated_at = now()
        WHERE status = 'depositing'
    """
    async with pool.acquire() as conn:
        result = await conn.execute(query)
    parts = result.split()
    if len(parts) >= 2 and parts[0].upper() == "UPDATE":
        try:
            return int(parts[1])
        except ValueError:
            return 0
    return 0


async def list_deposited_for_source(
    source_id: UUID,
    *,
    since: datetime | None = None,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """Items `deposited` d'une source (+ provider de transcription), plus
    anciens dépôts d'abord. `since` : strictement postérieurs (curseur
    only_new de roles__get_corpus, cf. corpus_pull_cursors).
    """
    params: list[Any] = [source_id]
    since_clause = ""
    if since is not None:
        params.append(since)
        since_clause = f"AND si.deposited_at > ${len(params)} "

    query = (
        "SELECT si.*, tj.provider_used "
        "FROM source_items si "
        "LEFT JOIN LATERAL ("
        "    SELECT provider_used FROM transcription_jobs"
        "    WHERE source_item_id = si.id AND provider_used IS NOT NULL"
        "    ORDER BY completed_at DESC NULLS LAST LIMIT 1"
        ") tj ON true "
        "WHERE si.source_id = $1 AND si.status = 'deposited' "
        f"{since_clause}"
        "ORDER BY si.deposited_at ASC"
    )
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, *params)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]
