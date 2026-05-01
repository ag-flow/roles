"""Stats agrégées du corpus d'un role_project.

Petit helper utilisé par services/github_publish/publisher.py pour
afficher des compteurs dans le README publié sur GitHub. Restera utile
si d'autres consommateurs (UI, exports) en ont besoin.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

# Compteur sources + chunks en 1 round-trip via SELECT (...) AS x.
_STATS_SQL = """
    SELECT
        (SELECT count(*) FROM sources WHERE role_project_id = $1) AS source_count,
        (SELECT count(*) FROM corpus_chunks WHERE role_project_id = $1) AS chunk_count
"""


async def get_corpus_stats(
    role_project_id: UUID, *, pool: asyncpg.Pool,
) -> dict[str, int]:
    """Retourne ``{"source_count": N, "chunk_count": M}`` pour un role_project."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_STATS_SQL, role_project_id)
    if row is None:
        return {"source_count": 0, "chunk_count": 0}
    return {
        "source_count": int(row["source_count"]),
        "chunk_count": int(row["chunk_count"]),
    }
