"""CRUD asyncpg pour role_publication_config (Sprint 8).

Une config par projet (PRIMARY KEY sur role_project_id). Inclut le choix
de licence du rôle publié (cf. migration 0013).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

_GET_SQL = """
    SELECT role_project_id, repo_full_name, target_subdirectory, branch,
           commit_message_template, license_choice, created_at, updated_at
    FROM role_publication_config
    WHERE role_project_id = $1
"""

_UPSERT_SQL = """
    INSERT INTO role_publication_config
        (role_project_id, repo_full_name, target_subdirectory, branch,
         commit_message_template, license_choice)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (role_project_id) DO UPDATE SET
        repo_full_name = EXCLUDED.repo_full_name,
        target_subdirectory = EXCLUDED.target_subdirectory,
        branch = EXCLUDED.branch,
        commit_message_template = EXCLUDED.commit_message_template,
        license_choice = EXCLUDED.license_choice,
        updated_at = now()
"""


async def get_by_project_id(
    project_id: UUID,
    *,
    pool: asyncpg.Pool,
) -> dict | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_SQL, project_id)
    return dict(row) if row is not None and not isinstance(row, dict) else row


async def upsert(
    *,
    role_project_id: UUID,
    repo_full_name: str,
    target_subdirectory: str,
    branch: str,
    commit_message_template: str,
    license_choice: str,
    pool: asyncpg.Pool,
) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            _UPSERT_SQL,
            role_project_id,
            repo_full_name,
            target_subdirectory,
            branch,
            commit_message_template,
            license_choice,
        )
