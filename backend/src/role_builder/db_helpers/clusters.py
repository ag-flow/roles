"""CRUD asyncpg pour la table ``clusters`` (migration 0008).

Les clusters sont produits par l'étage clusterer — chaque cluster
regroupe des signaux thématiquement cohérents.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

_INSERT_CLUSTER_SQL = """
    INSERT INTO clusters
        (run_id, role_project_id, tenant_id, name, description, signal_ids)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id
"""

_LIST_BY_RUN_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, name, description,
           signal_ids, created_at
    FROM clusters
    WHERE run_id = $1
    ORDER BY created_at ASC
"""

_LIST_BY_PROJECT_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, name, description,
           signal_ids, created_at
    FROM clusters
    WHERE role_project_id = $1
    ORDER BY created_at DESC
"""

_DELETE_BY_RUN_SQL = "DELETE FROM clusters WHERE run_id = $1"


async def insert_cluster(
    *,
    run_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    name: str,
    description: str | None,
    signal_ids: list[UUID],
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT un cluster et retourne son UUID.

    ``signal_ids`` est passé tel quel (asyncpg gère uuid[] natif).
    """
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            _INSERT_CLUSTER_SQL,
            run_id,
            role_project_id,
            tenant_id,
            name,
            description,
            signal_ids,
        )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def list_clusters_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """Retourne les clusters d'un run, triés par created_at ASC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_RUN_SQL, run_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_clusters_by_project(role_project_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """Retourne les clusters d'un projet, triés par created_at DESC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_PROJECT_SQL, role_project_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def delete_clusters_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Supprime tous les clusters d'un run. Retourne le count supprimé."""
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_RUN_SQL, run_id)
    # asyncpg execute retourne "DELETE N"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
