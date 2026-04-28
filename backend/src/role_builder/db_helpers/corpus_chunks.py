"""CRUD asyncpg pour la table ``corpus_chunks`` (cf. migration 0004).

L'extension ``pgvector`` n'est pas auto-enregistrée côté asyncpg : on
sérialise les embeddings au format texte ``'[v1,v2,...]'`` et on cast
en ``vector`` côté SQL via ``$X::vector``.

Recherche sémantique : opérateur ``<=>`` (cosine distance) ordonné ASC,
puis Python convertit ``distance → similarity = 1 - distance``.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

_INSERT_CHUNK_SQL = """
    INSERT INTO corpus_chunks
        (source_item_id, role_project_id, tenant_id, chunk_index,
         start_s, end_s, text, embedding)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
"""

_SEMANTIC_SEARCH_SQL = """
    SELECT
        cc.id AS chunk_id,
        cc.source_item_id,
        cc.text,
        cc.start_s,
        cc.end_s,
        si.title AS source_title,
        (cc.embedding <=> $2::vector) AS distance
    FROM corpus_chunks cc
    LEFT JOIN source_items si ON si.id = cc.source_item_id
    WHERE cc.role_project_id = $1
    ORDER BY cc.embedding <=> $2::vector ASC
    LIMIT $3
"""

_LIST_BY_ITEM_SQL = """
    SELECT id, source_item_id, role_project_id, chunk_index,
           start_s, end_s, text, created_at
    FROM corpus_chunks
    WHERE source_item_id = $1
    ORDER BY chunk_index ASC
    LIMIT $2 OFFSET $3
"""

_LIST_BY_PROJECT_SQL = """
    SELECT cc.id, cc.source_item_id, cc.role_project_id, cc.chunk_index,
           cc.start_s, cc.end_s, cc.text, cc.created_at,
           si.title AS source_title
    FROM corpus_chunks cc
    JOIN source_items si ON si.id = cc.source_item_id
    WHERE cc.role_project_id = $1
    ORDER BY cc.created_at DESC
    LIMIT $2 OFFSET $3
"""

_COUNT_BY_PROJECT_SQL = """
    SELECT count(*) FROM corpus_chunks WHERE role_project_id = $1
"""


def _embedding_to_pgvector_literal(vec: list[float]) -> str:
    """Sérialise une liste de floats au format pgvector ``'[v1,v2,...]'``."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


async def insert_chunks_bulk(
    chunks: list[dict[str, Any]],
    *,
    source_item_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    pool: asyncpg.Pool,
) -> int:
    """Bulk-insert des chunks via executemany. Retourne le count inséré.

    Chaque chunk attendu : ``{chunk_index, start_s, end_s, text, embedding}``.
    Liste vide → 0 sans appel SQL.
    """
    if not chunks:
        return 0

    rows = [
        (
            source_item_id,
            role_project_id,
            tenant_id,
            int(c["chunk_index"]),
            (None if c.get("start_s") is None else float(c["start_s"])),
            (None if c.get("end_s") is None else float(c["end_s"])),
            str(c["text"]),
            _embedding_to_pgvector_literal(list(c["embedding"])),
        )
        for c in chunks
    ]
    async with pool.acquire() as conn:
        await conn.executemany(_INSERT_CHUNK_SQL, rows)
    return len(rows)


async def semantic_search(
    *,
    role_project_id: UUID,
    query_embedding: list[float],
    limit: int = 20,
    min_similarity: float = 0.0,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """ANN search pgvector ``<=>`` (cosine). Retourne dicts avec ``similarity``.

    similarity = 1 - cosine_distance. Filtre côté Python sur ``min_similarity``.
    """
    embed_literal = _embedding_to_pgvector_literal(query_embedding)
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SEMANTIC_SEARCH_SQL, role_project_id, embed_literal, limit)

    results: list[dict[str, Any]] = []
    for r in rows:
        row = dict(r) if not isinstance(r, dict) else r
        distance = float(row.get("distance") or 0.0)
        similarity = 1.0 - distance
        if similarity < min_similarity:
            continue
        row_out = dict(row)
        row_out["similarity"] = similarity
        results.append(row_out)
    return results


async def list_by_item(
    source_item_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List chunks d'un source_item ordonnés par chunk_index."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_ITEM_SQL, source_item_id, limit, offset)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_by_project(
    role_project_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """List chunks d'un role_project (tous source_items confondus), récents d'abord.

    Joint ``source_items`` pour exposer ``source_title`` côté API.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_PROJECT_SQL, role_project_id, limit, offset)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def count_by_project(role_project_id: UUID, *, pool: asyncpg.Pool) -> int:
    """COUNT(*) des chunks d'un role_project."""
    async with pool.acquire() as conn:
        n = await conn.fetchval(_COUNT_BY_PROJECT_SQL, role_project_id)
    return int(n or 0)
