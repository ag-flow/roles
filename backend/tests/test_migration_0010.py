"""Test d'intégration de la migration 0010 (drop vault_secret_name + invalidation legacy).

Même pattern que test_migration_0009.py : Postgres réel éphémère,
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
    "0008_upload_intake.sql",
    "0009_user_wallets_secrets.sql",
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
    """Connexion à une base éphémère fraîche (migrations 0001..0009), détruite en fin de test."""
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


async def _insert_local_secret(db: asyncpg.Connection, user_id: uuid.UUID) -> uuid.UUID:
    return await db.fetchval(
        """
        INSERT INTO user_secrets
            (tenant_id, user_id, secret_type, label, storage, value_encrypted)
        VALUES ($1, $2, 'openai-whisper', 'k', 'local', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        b"v",
    )


async def test_0010_legacy_rows_invalidated_and_column_dropped(
    db: asyncpg.Connection,
) -> None:
    """Lignes sans secret_id → invalid ; lignes migrées intactes ; colonne droppée."""
    user_id = uuid.uuid4()
    secret_id = await _insert_local_secret(db, user_id)

    legacy_key = await db.fetchval(
        """
        INSERT INTO user_transcription_keys
            (tenant_id, user_id, provider, vault_secret_name, status)
        VALUES ($1, $2, 'deepgram', '${vault://api1:users/x/y}', 'active')
        RETURNING id
        """,
        TENANT_ID,
        user_id,
    )
    migrated_key = await db.fetchval(
        """
        INSERT INTO user_transcription_keys
            (tenant_id, user_id, provider, vault_secret_name, status, secret_id)
        VALUES ($1, $2, 'openai-whisper', 'unused', 'active', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        secret_id,
    )
    legacy_cred = await db.fetchval(
        """
        INSERT INTO user_credentials
            (tenant_id, user_id, platform, vault_secret_name, status)
        VALUES ($1, $2, 'youtube', 'users/x/scraping/youtube/z', 'active')
        RETURNING id
        """,
        TENANT_ID,
        user_id,
    )

    await _apply(db, "0010_drop_vault_secret_name.sql")

    assert (
        await db.fetchval(
            "SELECT status FROM user_transcription_keys WHERE id = $1", legacy_key
        )
        == "invalid"
    )
    assert (
        await db.fetchval(
            "SELECT status FROM user_transcription_keys WHERE id = $1", migrated_key
        )
        == "active"
    )
    assert (
        await db.fetchval("SELECT status FROM user_credentials WHERE id = $1", legacy_cred)
        == "invalid"
    )

    for table in ("user_transcription_keys", "user_credentials"):
        cols = [
            r["column_name"]
            for r in await db.fetch(
                "SELECT column_name FROM information_schema.columns WHERE table_name = $1",
                table,
            )
        ]
        assert "vault_secret_name" not in cols
        assert "secret_id" in cols


async def test_0010_new_rows_insertable_with_secret_id_only(db: asyncpg.Connection) -> None:
    """Après 0010, une ligne de service s'insère avec secret_id sans colonne vault."""
    await _apply(db, "0010_drop_vault_secret_name.sql")

    user_id = uuid.uuid4()
    secret_id = await _insert_local_secret(db, user_id)

    key_id = await db.fetchval(
        """
        INSERT INTO user_transcription_keys
            (tenant_id, user_id, provider, status, secret_id)
        VALUES ($1, $2, 'openai-whisper', 'active', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        secret_id,
    )
    assert key_id is not None
