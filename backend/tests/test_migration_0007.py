"""Test d'intégration de la migration 0007 (façade MCP roles__* — lot scrape).

Même pattern que test_migration_0005_0006.py : Postgres réel éphémère,
skip proprement si TEST_DATABASE_ADMIN_URL n'est pas joignable.
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://rb:changeme_in_real_env@localhost:5432/postgres",
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def _postgres_reachable() -> bool:
    try:
        conn = await asyncpg.connect(dsn=ADMIN_DSN, timeout=2)
    except (OSError, asyncpg.PostgresError):
        return False
    await conn.close()
    return True


def _migration_sql(filename: str) -> str:
    return (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")


async def _apply(conn: asyncpg.Connection, filename: str) -> None:
    await conn.execute(_migration_sql(filename))


@pytest.fixture
async def db(request: pytest.FixtureRequest) -> AsyncIterator[asyncpg.Connection]:
    """Connexion à une base éphémère fraîche, détruite en fin de test."""
    if not await _postgres_reachable():
        pytest.skip(f"Postgres non joignable via TEST_DATABASE_ADMIN_URL ({ADMIN_DSN})")

    db_name = f"rb_migtest_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    target_dsn = re.sub(r"/[^/]+$", f"/{db_name}", ADMIN_DSN)
    conn = await asyncpg.connect(dsn=target_dsn)
    try:
        yield conn
    finally:
        await conn.close()
        admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


async def _apply_full_chain(conn: asyncpg.Connection) -> None:
    for filename in (
        "0001_initial_schema.sql",
        "0002_vault_secret_name.sql",
        "0003_vault_user_credentials.sql",
        "0004_vault_github_integrations.sql",
        "0005_acquisition_requests.sql",
        "0006_drop_synthesis_tables.sql",
        "0007_acquisition_facade.sql",
    ):
        await _apply(conn, filename)


async def test_sources_insertable_without_role_project(db: asyncpg.Connection) -> None:
    """Une source V2 (façade MCP) n'a plus besoin de role_project_id."""
    await _apply_full_chain(db)

    source_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO sources (id, role_project_id, tenant_id, platform, source_type, url, status)
        VALUES ($1, NULL, $2, 'youtube', 'channel', 'https://youtube.com/@clea-ux', 'pending_discovery')
        """,
        source_id,
        TENANT_ID,
    )

    role_project_id = await db.fetchval(
        "SELECT role_project_id FROM sources WHERE id = $1", source_id
    )
    assert role_project_id is None


async def test_source_items_accept_description_excerpt_and_tags(db: asyncpg.Connection) -> None:
    """Les colonnes riches list_discovered existent et sont peuplables."""
    await _apply_full_chain(db)

    source_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO sources (id, role_project_id, tenant_id, platform, source_type, url, status)
        VALUES ($1, NULL, $2, 'youtube', 'channel', 'https://youtube.com/@clea-ux', 'discovered')
        """,
        source_id,
        TENANT_ID,
    )
    item_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO source_items
            (id, source_id, tenant_id, platform_item_id, title, status,
             description_excerpt, tags)
        VALUES ($1, $2, $3, 'yt-abc123', 'Interview UX', 'pending_download', $4, $5)
        """,
        item_id,
        source_id,
        TENANT_ID,
        "Dans cette vidéo je partage ma méthode…",
        ["ux", "user research"],
    )

    row = await db.fetchrow(
        "SELECT description_excerpt, tags FROM source_items WHERE id = $1", item_id
    )
    assert row["description_excerpt"] == "Dans cette vidéo je partage ma méthode…"
    assert row["tags"] == ["ux", "user research"]


async def test_v1_sources_keep_role_project_id_after_migration(db: asyncpg.Connection) -> None:
    """Migration 0007 est additive : les sources V1 existantes ne perdent rien."""
    await _apply_full_chain(db)

    role_project_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO role_projects (id, tenant_id, user_id, display_name, keep_audio)
        VALUES ($1, $2, $3, 'Projet V1', true)
        """,
        role_project_id,
        TENANT_ID,
        user_id,
    )
    source_id = uuid.uuid4()
    await db.execute(
        """
        INSERT INTO sources (id, role_project_id, tenant_id, platform, source_type, url, status)
        VALUES ($1, $2, $3, 'youtube', 'channel', 'https://youtube.com/@old', 'discovered')
        """,
        source_id,
        role_project_id,
        TENANT_ID,
    )

    fetched = await db.fetchval("SELECT role_project_id FROM sources WHERE id = $1", source_id)
    assert fetched == role_project_id
