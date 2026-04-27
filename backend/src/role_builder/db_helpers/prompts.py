"""CRUD asyncpg pour les tables ``prompts`` et ``prompt_versions`` (migration 0008).

L'index unique partiel ``prompt_versions_one_system_default (prompt_id)
WHERE is_system_default = true`` garantit qu'une seule version active existe
par prompt. Lors d'un insert avec ``is_system_default=True``, on désactive
d'abord l'ancienne via UPDATE avant de faire l'INSERT.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

_UPSERT_PROMPT_SQL = """
    INSERT INTO prompts (name, type, target_section, description)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (name)
    DO UPDATE SET
        type = EXCLUDED.type,
        target_section = EXCLUDED.target_section,
        description = EXCLUDED.description
    RETURNING id
"""

_GET_PROMPT_BY_NAME_SQL = """
    SELECT id, name, type, target_section, description, created_at
    FROM prompts
    WHERE name = $1
"""

_LIST_PROMPTS_SQL = """
    SELECT id, name, type, target_section, description, created_at
    FROM prompts
    ORDER BY name ASC
"""

_INSERT_VERSION_SQL = """
    INSERT INTO prompt_versions
        (prompt_id, version_number, template, parameters_schema,
         is_system_default, created_by)
    VALUES ($1, $2, $3, $4, $5, $6)
    RETURNING id
"""

_DISABLE_SYSTEM_DEFAULT_SQL = """
    UPDATE prompt_versions
    SET is_system_default = false
    WHERE prompt_id = $1 AND is_system_default = true
"""

_GET_SYSTEM_DEFAULT_SQL = """
    SELECT pv.id, pv.prompt_id, pv.version_number, pv.template,
           pv.parameters_schema, pv.is_system_default, pv.created_by,
           pv.created_at, p.name AS prompt_name
    FROM prompt_versions pv
    JOIN prompts p ON pv.prompt_id = p.id
    WHERE p.name = $1 AND pv.is_system_default = true
    LIMIT 1
"""

_LIST_VERSIONS_SQL = """
    SELECT id, prompt_id, version_number, template, parameters_schema,
           is_system_default, created_by, created_at
    FROM prompt_versions
    WHERE prompt_id = $1
    ORDER BY version_number DESC
"""

_GET_VERSION_BY_ID_SQL = """
    SELECT id, prompt_id, version_number, template, parameters_schema,
           is_system_default, created_by, created_at
    FROM prompt_versions
    WHERE id = $1
"""

_DISABLE_ALL_SYSTEM_DEFAULTS_SQL = """
    UPDATE prompt_versions
    SET is_system_default = false
    WHERE prompt_id = $1 AND is_system_default = true AND id != $2
"""

_SET_VERSION_DEFAULT_SQL = """
    UPDATE prompt_versions
    SET is_system_default = true
    WHERE id = $1 AND prompt_id = $2
    RETURNING id
"""


async def upsert_prompt(
    *,
    name: str,
    type: str,
    target_section: str | None = None,
    description: str | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT...ON CONFLICT(name) DO UPDATE. Retourne l'id via fetchval."""
    async with pool.acquire() as conn:
        result = await conn.fetchval(_UPSERT_PROMPT_SQL, name, type, target_section, description)
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def get_prompt_by_name(name: str, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Retourne le prompt par son name, ou None s'il n'existe pas."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_PROMPT_BY_NAME_SQL, name)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def list_prompts(*, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Retourne tous les prompts triés par name."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_PROMPTS_SQL)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def insert_prompt_version(
    *,
    prompt_id: UUID,
    version_number: int,
    template: str,
    parameters_schema: dict[str, Any] | None = None,
    is_system_default: bool = False,
    created_by: UUID | None = None,
    pool: asyncpg.Pool,
) -> UUID:
    """Insère une nouvelle version de prompt.

    Si ``is_system_default=True`` : désactive l'ancien default via UPDATE
    (pour respecter l'index unique partiel), puis insère la nouvelle version.
    Le ``parameters_schema`` est sérialisé en JSON si c'est un dict.
    """
    schema_json = json.dumps(parameters_schema) if parameters_schema is not None else None

    async with pool.acquire() as conn:
        if is_system_default:
            async with conn.transaction():
                await conn.execute(_DISABLE_SYSTEM_DEFAULT_SQL, prompt_id)
                result = await conn.fetchval(
                    _INSERT_VERSION_SQL,
                    prompt_id,
                    version_number,
                    template,
                    schema_json,
                    is_system_default,
                    created_by,
                )
        else:
            result = await conn.fetchval(
                _INSERT_VERSION_SQL,
                prompt_id,
                version_number,
                template,
                schema_json,
                is_system_default,
                created_by,
            )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def get_system_default_version(
    prompt_name: str, *, pool: asyncpg.Pool
) -> dict[str, Any] | None:
    """Retourne la version system_default d'un prompt (joint prompts + prompt_versions).

    Retourne tous les champs de prompt_versions + prompt_name.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_SYSTEM_DEFAULT_SQL, prompt_name)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def list_versions(prompt_id: UUID, *, pool: asyncpg.Pool) -> list[dict[str, Any]]:
    """Retourne les versions d'un prompt triées par version_number DESC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_VERSIONS_SQL, prompt_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def get_version_by_id(version_id: UUID, *, pool: asyncpg.Pool) -> dict[str, Any] | None:
    """Retourne une version par son id, ou None."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_VERSION_BY_ID_SQL, version_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def set_system_default(
    prompt_id: UUID,
    version_id: UUID,
    *,
    pool: asyncpg.Pool,
) -> None:
    """Promeut version_id comme system_default pour prompt_id (transaction).

    Désactive toutes les autres versions du même prompt, puis active version_id.
    """
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(_DISABLE_ALL_SYSTEM_DEFAULTS_SQL, prompt_id, version_id)
            result = await conn.fetchval(_SET_VERSION_DEFAULT_SQL, version_id, prompt_id)
            if result is None:
                raise ValueError("version_id does not belong to prompt_id")
