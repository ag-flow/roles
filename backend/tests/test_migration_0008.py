"""Test d'intégration de la migration 0008 (intake par upload direct).

Même pattern que test_migration_0007.py : Postgres réel éphémère,
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

PRIOR_MIGRATIONS = (
    "0001_initial_schema.sql",
    "0002_vault_secret_name.sql",
    "0003_vault_user_credentials.sql",
    "0004_vault_github_integrations.sql",
    "0005_acquisition_requests.sql",
    "0006_drop_synthesis_tables.sql",
    "0007_acquisition_facade.sql",
)


async def _postgres_reachable() -> bool:
    try:
        conn = await asyncpg.connect(dsn=ADMIN_DSN, timeout=2)
    except (OSError, asyncpg.PostgresError):
        return False
    await conn.close()
    return True


async def _apply(conn: asyncpg.Connection, filename: str) -> None:
    await conn.execute((MIGRATIONS_DIR / filename).read_text(encoding="utf-8"))


@pytest.fixture
async def db(request: pytest.FixtureRequest) -> AsyncIterator[asyncpg.Connection]:
    """Connexion à une base éphémère fraîche (migrations 0001..0007), détruite en fin de test."""
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
    for filename in PRIOR_MIGRATIONS:
        await _apply(conn, filename)

    try:
        yield conn
    finally:
        await conn.close()
        admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


async def test_0008_sources_url_nullable_and_upload_columns(db: asyncpg.Connection) -> None:
    """Après 0008 : source technique upload sans URL + colonnes de slot sur source_items."""
    await _apply(db, "0008_upload_intake.sql")

    source_id = await db.fetchval(
        """
        INSERT INTO sources (role_project_id, tenant_id, platform, source_type, url)
        VALUES (NULL, $1, 'upload', 'upload', NULL)
        RETURNING id
        """,
        TENANT_ID,
    )
    assert source_id is not None

    item_id = await db.fetchval(
        """
        INSERT INTO source_items
            (source_id, tenant_id, platform_item_id, status,
             upload_media_type, upload_s3_key, upload_expires_at)
        VALUES ($1, $2, 'upload-abc123', 'awaiting_upload',
                'video/mp4', 'upload/up-conf/abc.mp4', now() + interval '1 hour')
        RETURNING id
        """,
        source_id,
        TENANT_ID,
    )
    row = await db.fetchrow("SELECT * FROM source_items WHERE id = $1", item_id)
    assert row["upload_media_type"] == "video/mp4"
    assert row["upload_s3_key"] == "upload/up-conf/abc.mp4"
    assert row["upload_expires_at"] is not None


async def test_0008_partial_index_on_awaiting_upload(db: asyncpg.Connection) -> None:
    """L'index partiel du nettoyage périodique existe et cible awaiting_upload."""
    await _apply(db, "0008_upload_intake.sql")

    indexdef = await db.fetchval(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'source_items_awaiting_upload_idx'"
    )
    assert indexdef is not None
    assert "awaiting_upload" in indexdef
    assert "upload_expires_at" in indexdef


async def test_0008_scrape_sources_keep_their_url(db: asyncpg.Connection) -> None:
    """Les sources scrape existantes ne sont pas affectées (url conservée)."""
    source_id = await db.fetchval(
        """
        INSERT INTO sources (role_project_id, tenant_id, platform, source_type, url)
        VALUES (NULL, $1, 'youtube', 'channel', 'https://youtube.com/@clea-ux')
        RETURNING id
        """,
        TENANT_ID,
    )
    await _apply(db, "0008_upload_intake.sql")

    url = await db.fetchval("SELECT url FROM sources WHERE id = $1", source_id)
    assert url == "https://youtube.com/@clea-ux"
