"""CRUD asyncpg pour la table ``runs`` (migration 0008).

Gestion du cycle de vie d'un run de synthèse :
pending → running → done | failed.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

_CREATE_RUN_SQL = """
    INSERT INTO runs
        (role_project_id, tenant_id, prompt_version_id, input_summary,
         parameters, instruction_override, status)
    VALUES ($1, $2, $3, $4, $5, $6, 'pending')
    RETURNING id
"""

_MARK_RUNNING_SQL = """
    UPDATE runs
    SET status = 'running', started_at = now()
    WHERE id = $1
"""

_MARK_DONE_SQL = """
    UPDATE runs
    SET status = 'done', output = $2, llm_provider = $3, llm_model = $4,
        tokens_input = $5, tokens_output = $6, cost_usd = $7, completed_at = now()
    WHERE id = $1
"""

_MARK_FAILED_SQL = """
    UPDATE runs
    SET status = 'failed', error = $2, completed_at = now()
    WHERE id = $1
"""

_LIST_RUNS_SQL = """
    SELECT *
    FROM runs
    WHERE role_project_id = $1
    ORDER BY created_at DESC
    LIMIT $2
"""

_LIST_RUNS_WITH_STATUS_SQL = """
    SELECT *
    FROM runs
    WHERE role_project_id = $1
    AND status = $2
    ORDER BY created_at DESC
    LIMIT $3
"""

_GET_RUN_SQL = """
    SELECT *
    FROM runs
    WHERE id = $1
"""


async def create_run(
    *,
    role_project_id: UUID,
    tenant_id: UUID,
    prompt_version_id: UUID,
    input_summary: dict[str, Any] | None = None,
    parameters: dict[str, Any] | None = None,
    instruction_override: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT un nouveau run avec status='pending'. Retourne l'id.

    ``input_summary`` et ``parameters`` sont sérialisés en JSON si non-None.
    """
    input_summary_json = json.dumps(input_summary) if input_summary is not None else None
    parameters_json = json.dumps(parameters) if parameters is not None else None

    async with pool.acquire() as conn:
        result = await conn.fetchval(
            _CREATE_RUN_SQL,
            role_project_id,
            tenant_id,
            prompt_version_id,
            input_summary_json,
            parameters_json,
            instruction_override,
        )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def mark_running(run_id: UUID, *, pool: asyncpg.Pool) -> None:
    """UPDATE status='running', started_at=now()."""
    async with pool.acquire() as conn:
        await conn.execute(_MARK_RUNNING_SQL, run_id)


async def mark_done(
    run_id: UUID,
    *,
    output: str | None,
    llm_provider: str = "mistral",
    llm_model: str,
    tokens_input: int,
    tokens_output: int,
    cost_usd: float,
    pool: asyncpg.Pool,
) -> None:
    """UPDATE status='done' avec le résultat LLM + métriques de coût."""
    async with pool.acquire() as conn:
        await conn.execute(
            _MARK_DONE_SQL,
            run_id,
            output,
            llm_provider,
            llm_model,
            tokens_input,
            tokens_output,
            cost_usd,
        )


async def mark_failed(run_id: UUID, error: str, *, pool: asyncpg.Pool) -> None:
    """UPDATE status='failed', error=$2, completed_at=now()."""
    async with pool.acquire() as conn:
        await conn.execute(_MARK_FAILED_SQL, run_id, error)


async def list_runs(
    role_project_id: UUID,
    *,
    status: str | None = None,
    limit: int = 50,
    pool: asyncpg.Pool,
) -> list[dict[str, Any]]:
    """Retourne les runs d'un projet, triés par created_at DESC.

    Si ``status`` est fourni, filtre sur ce statut.
    """
    async with pool.acquire() as conn:
        if status is not None:
            rows = await conn.fetch(_LIST_RUNS_WITH_STATUS_SQL, role_project_id, status, limit)
        else:
            rows = await conn.fetch(_LIST_RUNS_SQL, role_project_id, limit)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_run(run_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Retourne un run par son id, ou None."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_RUN_SQL, run_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


# ---------------------------------------------------------------------------
# Phase 2 sous-projet C : marquage obsolescence
# ---------------------------------------------------------------------------

_MARK_OBSOLETE_FOR_PROJECT_SQL = """
    UPDATE runs SET is_obsolete = true
    WHERE role_project_id = $1 AND is_obsolete = false
"""

_MARK_OBSOLETE_FOR_PROMPT_SQL = """
    UPDATE runs SET is_obsolete = true
    WHERE prompt_version_id IN (
        SELECT id FROM prompt_versions
        WHERE prompt_id = $1 AND id != $2
    )
    AND is_obsolete = false
"""


def _rowcount(tag: str) -> int:
    """Parse le tag retourné par asyncpg.execute (ex: 'UPDATE 5')."""
    try:
        return int(tag.split()[-1])
    except (IndexError, ValueError):
        return 0


async def mark_obsolete_for_project(
    role_project_id: UUID, *, pool: asyncpg.Pool,
) -> int:
    """Marque obsolete tous les runs encore actifs d'un role_project.

    Appelé quand role_projects.global_directives est édité. Retourne le
    nombre de lignes touchées.
    """
    async with pool.acquire() as conn:
        tag = await conn.execute(_MARK_OBSOLETE_FOR_PROJECT_SQL, role_project_id)
    return _rowcount(tag)


async def mark_obsolete_for_prompt(
    prompt_id: UUID, *, except_version_id: UUID, pool: asyncpg.Pool,
) -> int:
    """Marque obsolete les runs ayant utilisé une autre version du prompt.

    Appelé après set_system_default(prompt_id, new_version_id). La nouvelle
    version system_default n'est pas affectée — les runs qui l'ont utilisée
    restent valides.
    """
    async with pool.acquire() as conn:
        tag = await conn.execute(
            _MARK_OBSOLETE_FOR_PROMPT_SQL, prompt_id, except_version_id,
        )
    return _rowcount(tag)
