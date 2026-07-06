"""CRUD asyncpg pour `corpus_pull_cursors` (cf. migration 0005).

Curseur de livraison incrémentale par `(request_id, caller)` : mémorise le
`deposited_at` le plus récent servi à un appelant, pour que `only_new` de
`roles__get_corpus` ne retourne que les dépôts postérieurs (spec v2/01 §2.4).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg


async def get_last_pulled_at(
    request_id: UUID, caller: str, *, pool: asyncpg.Pool
) -> datetime | None:
    """Curseur d'un appelant sur une requête ; None si jamais pullé."""
    query = """
        SELECT last_pulled_at FROM corpus_pull_cursors
        WHERE request_id = $1 AND caller = $2
    """
    async with pool.acquire() as conn:
        return await conn.fetchval(query, request_id, caller)


async def upsert_cursor(
    request_id: UUID, caller: str, last_pulled_at: datetime, *, pool: asyncpg.Pool
) -> None:
    """Crée ou avance le curseur d'un appelant sur une requête.

    `GREATEST` : deux pulls quasi simultanés du même appelant peuvent commiter
    dans l'ordre inverse ; sans ça le curseur reculerait et le pull `only_new`
    suivant re-servirait des documents déjà vus (BUG-25).
    """
    query = """
        INSERT INTO corpus_pull_cursors (request_id, caller, last_pulled_at)
        VALUES ($1, $2, $3)
        ON CONFLICT (request_id, caller)
        DO UPDATE SET last_pulled_at =
            GREATEST(corpus_pull_cursors.last_pulled_at, EXCLUDED.last_pulled_at)
    """
    async with pool.acquire() as conn:
        await conn.execute(query, request_id, caller, last_pulled_at)
