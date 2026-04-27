"""CRUD asyncpg pour la table ``document_plans`` (migration 0008).

Les document_plans sont produits par l'étage decomposer — chaque plan
décrit les documents atomiques à rédiger pour une section du rôle.
"""

from __future__ import annotations

import json
from uuid import UUID

import asyncpg

_INSERT_PLAN_SQL = """
    INSERT INTO document_plans
        (run_id, role_project_id, tenant_id, section, planned_documents)
    VALUES ($1, $2, $3, $4, $5)
    RETURNING id
"""

_LIST_BY_RUN_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, section,
           planned_documents, created_at
    FROM document_plans
    WHERE run_id = $1
    ORDER BY created_at ASC
"""

_LIST_BY_PROJECT_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, section,
           planned_documents, created_at
    FROM document_plans
    WHERE role_project_id = $1
    ORDER BY created_at DESC
"""

_LIST_BY_PROJECT_FILTERED_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, section,
           planned_documents, created_at
    FROM document_plans
    WHERE role_project_id = $1
    AND section = $2
    ORDER BY created_at DESC
"""

_GET_LATEST_PER_SECTION_SQL = """
    SELECT DISTINCT ON (section)
           id, run_id, role_project_id, tenant_id, section,
           planned_documents, created_at
    FROM document_plans
    WHERE role_project_id = $1
    ORDER BY section, created_at DESC
"""

_GET_BY_ID_SQL = """
    SELECT id, run_id, role_project_id, tenant_id, section,
           planned_documents, created_at
    FROM document_plans
    WHERE id = $1
"""

_DELETE_BY_RUN_SQL = "DELETE FROM document_plans WHERE run_id = $1"


async def insert_document_plan(
    *,
    run_id: UUID,
    role_project_id: UUID,
    tenant_id: UUID,
    section: str,
    planned_documents: list[dict],
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT un plan de documents et retourne son UUID.

    ``planned_documents`` est sérialisé via json.dumps avant INSERT.
    Format attendu : list de {name, brief, supporting_signals: [signal_id, ...]}.
    """
    planned_documents_json = json.dumps(planned_documents)
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            _INSERT_PLAN_SQL,
            run_id,
            role_project_id,
            tenant_id,
            section,
            planned_documents_json,
        )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def list_plans_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """Retourne les plans d'un run, triés par created_at ASC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_BY_RUN_SQL, run_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_plans_by_project(
    role_project_id: UUID,
    *,
    section: str | None = None,
    pool: asyncpg.Pool,
) -> list[dict]:
    """Retourne les plans d'un projet, triés par created_at DESC.

    Si ``section`` est fourni, filtre sur cette section.
    """
    async with pool.acquire() as conn:
        if section is not None:
            rows = await conn.fetch(_LIST_BY_PROJECT_FILTERED_SQL, role_project_id, section)
        else:
            rows = await conn.fetch(_LIST_BY_PROJECT_SQL, role_project_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_latest_plan_per_section(
    role_project_id: UUID, *, pool: asyncpg.Pool
) -> dict[str, dict]:
    """Retourne {section_name: plan_dict} avec le dernier plan par section.

    Utilise DISTINCT ON (section) pour récupérer le plan le plus récent
    par section en une seule requête.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(_GET_LATEST_PER_SECTION_SQL, role_project_id)
    result: dict[str, dict] = {}
    for row in rows:
        d = dict(row) if not isinstance(row, dict) else row
        result[d["section"]] = d
    return result


async def get_by_id(plan_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    """Retourne un plan par son id, ou None s'il n'existe pas."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_BY_ID_SQL, plan_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def delete_plans_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> int:
    """Supprime tous les plans d'un run. Retourne le count supprimé.

    Pour cleanup en cas d'échec du decomposer.
    """
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_RUN_SQL, run_id)
    # asyncpg execute retourne "DELETE N"
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
