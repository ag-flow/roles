"""CRUD asyncpg pour la table ``role_documents`` (migration 0008).

Les role_documents sont les documents atomiques produits par l'étage document_writer.
Chaque document est versionné : (role_project_id, section, name) peut avoir plusieurs versions,
une seule étant ``is_current=true`` à la fois (index unique partiel en DB).
"""

from __future__ import annotations

from uuid import UUID

import asyncpg

_VERSION_SQL = """
    SELECT COALESCE(MAX(version), 0) + 1
    FROM role_documents
    WHERE role_project_id = $1 AND section = $2 AND name = $3
"""

_INSERT_SQL = """
    INSERT INTO role_documents
        (role_project_id, tenant_id, section, name, content,
         source_run_id, version, is_current)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
    RETURNING id
"""

_DEMOTE_CURRENT_SQL = """
    UPDATE role_documents
    SET is_current = false, updated_at = now()
    WHERE role_project_id = $1 AND section = $2 AND name = $3
      AND is_current = true
"""

_GET_BY_ID_SQL = """
    SELECT id, role_project_id, tenant_id, section, name, content,
           source_run_id, version, is_current, locked, created_at, updated_at
    FROM role_documents
    WHERE id = $1
"""

_LIST_BY_SECTION_SQL = """
    SELECT id, role_project_id, tenant_id, section, name, content,
           source_run_id, version, is_current, locked, created_at, updated_at
    FROM role_documents
    WHERE role_project_id = $1 AND section = $2
    ORDER BY name ASC, version DESC
"""

_LIST_BY_SECTION_CURRENT_SQL = """
    SELECT id, role_project_id, tenant_id, section, name, content,
           source_run_id, version, is_current, locked, created_at, updated_at
    FROM role_documents
    WHERE role_project_id = $1 AND section = $2 AND is_current = true
    ORDER BY name ASC, version DESC
"""

_LIST_CURRENT_BY_PROJECT_SQL = """
    SELECT id, role_project_id, tenant_id, section, name, content,
           source_run_id, version, is_current, locked, created_at, updated_at
    FROM role_documents
    WHERE role_project_id = $1 AND is_current = true
    ORDER BY section ASC, name ASC
"""

_LIST_VERSIONS_SQL = """
    SELECT id, role_project_id, tenant_id, section, name, content,
           source_run_id, version, is_current, locked, created_at, updated_at
    FROM role_documents
    WHERE role_project_id = $1 AND section = $2 AND name = $3
    ORDER BY version DESC
"""

_GET_CONTEXT_SQL = """
    SELECT role_project_id, section, name
    FROM role_documents
    WHERE id = $1
"""

_DEMOTE_CURRENT_EXCL_SQL = """
    UPDATE role_documents
    SET is_current = false, updated_at = now()
    WHERE role_project_id = $1 AND section = $2 AND name = $3
      AND is_current = true AND id != $4
"""

_PROMOTE_SQL = """
    UPDATE role_documents
    SET is_current = true, updated_at = now()
    WHERE id = $1
"""

_LOCK_SQL = """
    UPDATE role_documents
    SET locked = true, updated_at = now()
    WHERE id = $1
"""

_UNLOCK_SQL = """
    UPDATE role_documents
    SET locked = false, updated_at = now()
    WHERE id = $1
"""

_DELETE_BY_RUN_SQL = "DELETE FROM role_documents WHERE source_run_id = $1"


async def insert_role_document(
    *,
    role_project_id: UUID,
    tenant_id: UUID,
    section: str,
    name: str,
    content: str,
    source_run_id: UUID,
    is_current: bool = False,
    pool: asyncpg.Pool,
) -> UUID:
    """INSERT un document versionné et retourne son UUID.

    Calcule version = max(version) + 1 pour (role_project_id, section, name).
    Si is_current=True : transaction qui d'abord UPDATE l'ancien current
    à false, puis INSERT avec is_current=true.
    """
    if is_current:
        async with pool.acquire() as conn:
            async with conn.transaction():
                version: int = await conn.fetchval(_VERSION_SQL, role_project_id, section, name)
                await conn.execute(_DEMOTE_CURRENT_SQL, role_project_id, section, name)
                result = await conn.fetchval(
                    _INSERT_SQL,
                    role_project_id,
                    tenant_id,
                    section,
                    name,
                    content,
                    source_run_id,
                    version,
                    True,
                )
    else:
        async with pool.acquire() as conn:
            version = await conn.fetchval(_VERSION_SQL, role_project_id, section, name)
            result = await conn.fetchval(
                _INSERT_SQL,
                role_project_id,
                tenant_id,
                section,
                name,
                content,
                source_run_id,
                version,
                False,
            )
    return UUID(str(result)) if not isinstance(result, UUID) else result


async def get_by_id(doc_id: UUID, *, pool: asyncpg.Pool) -> dict | None:
    """Retourne un document par son id, ou None s'il n'existe pas."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_BY_ID_SQL, doc_id)
    if row is None:
        return None
    return dict(row) if not isinstance(row, dict) else row


async def list_by_section(
    role_project_id: UUID,
    section: str,
    *,
    only_current: bool = False,
    pool: asyncpg.Pool,
) -> list[dict]:
    """Retourne les documents d'une section, ORDER BY name ASC, version DESC.

    Si only_current=True, filtre is_current=true.
    """
    query = _LIST_BY_SECTION_CURRENT_SQL if only_current else _LIST_BY_SECTION_SQL
    async with pool.acquire() as conn:
        rows = await conn.fetch(query, role_project_id, section)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_current_by_project(role_project_id: UUID, *, pool: asyncpg.Pool) -> list[dict]:
    """Tous les documents is_current=true du projet, tous sections confondues."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_CURRENT_BY_PROJECT_SQL, role_project_id)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def list_versions(
    role_project_id: UUID,
    section: str,
    name: str,
    *,
    pool: asyncpg.Pool,
) -> list[dict]:
    """Toutes les versions d'un document (project, section, name). ORDER BY version DESC."""
    async with pool.acquire() as conn:
        rows = await conn.fetch(_LIST_VERSIONS_SQL, role_project_id, section, name)
    return [dict(r) if not isinstance(r, dict) else r for r in rows]


async def set_current(doc_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Démote l'ancien current de (project, section, name) puis promote ce doc.

    Atomique (transaction). Lève ValueError si doc_id n'existe pas.
    """
    async with pool.acquire() as conn:
        row = await conn.fetchrow(_GET_CONTEXT_SQL, doc_id)
        if row is None:
            raise ValueError(f"doc_id {doc_id} not found in role_documents")
        context = dict(row) if not isinstance(row, dict) else row
        async with conn.transaction():
            await conn.execute(
                _DEMOTE_CURRENT_EXCL_SQL,
                context["role_project_id"],
                context["section"],
                context["name"],
                doc_id,
            )
            await conn.execute(_PROMOTE_SQL, doc_id)


async def lock_document(doc_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Verrouille un document (locked=true)."""
    async with pool.acquire() as conn:
        await conn.execute(_LOCK_SQL, doc_id)


async def unlock_document(doc_id: UUID, *, pool: asyncpg.Pool) -> None:
    """Déverrouille un document (locked=false)."""
    async with pool.acquire() as conn:
        await conn.execute(_UNLOCK_SQL, doc_id)


async def delete_documents_by_run(run_id: UUID, *, pool: asyncpg.Pool) -> int:
    """DELETE FROM role_documents WHERE source_run_id = $1, retourne count."""
    async with pool.acquire() as conn:
        result = await conn.execute(_DELETE_BY_RUN_SQL, run_id)
    try:
        return int(result.split()[-1])
    except (IndexError, ValueError):
        return 0
