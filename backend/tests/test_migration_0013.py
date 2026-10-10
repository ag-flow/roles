"""Test d'intégration de la migration 0013 (drop upload intake).

Même pattern que test_migration_0012.py : Postgres réel éphémère,
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
    "0010_drop_vault_secret_name.sql",
    "0011_drop_role_projects.sql",
    "0012_audio_path.sql",
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
async def pool(request: pytest.FixtureRequest) -> AsyncIterator[asyncpg.Connection]:
    """Connexion à une base éphémère fraîche (migrations 0001..0012), détruite en fin de test.

    Nommée `pool` pour reprendre la signature du brief, mais porte en réalité
    une connexion nue (`asyncpg.Connection`) — même pattern que les autres
    tests de migration de ce dépôt (test_migration_0012.py).
    """
    if not await _postgres_reachable():
        pytest.skip(f"Postgres non joignable via TEST_DATABASE_ADMIN_URL ({ADMIN_DSN})")

    db_name = f"rb_migtest_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        # f-string en DDL : exception NÉCESSAIRE et VOLONTAIRE (ruling de
        # l'architecte). asyncpg ne sait pas paramétrer un identifiant SQL —
        # `CREATE DATABASE $1` est invalide côté Postgres, pas seulement côté
        # pilote — et `db_name` n'est pas une entrée externe : il est construit
        # juste au-dessus à partir d'un UUID4 local, donc `[0-9a-f]{12}` après
        # un préfixe fixe. Ne pas "corriger" en requête paramétrée : ça ne
        # compile pas. L'identifiant reste entre guillemets doubles pour que
        # Postgres le traite comme un identifiant littéral.
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
            # Même exception volontaire qu'au CREATE ci-dessus : un identifiant
            # de base ne se paramètre pas, et db_name reste le même UUID local.
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


async def _columns(conn: asyncpg.Connection, table: str) -> set[str]:
    rows = await conn.fetch(
        "SELECT column_name FROM information_schema.columns WHERE table_name = $1", table
    )
    return {r["column_name"] for r in rows}


async def _insert_source(conn: asyncpg.Connection, *, platform: str = "youtube") -> uuid.UUID:
    return await conn.fetchval(
        """
        INSERT INTO sources (tenant_id, platform, source_type, url)
        VALUES ($1, $2, 'channel', 'https://youtube.com/@clea-ux')
        RETURNING id
        """,
        TENANT_ID,
        platform,
    )


async def test_migration_0013_drops_upload_columns(pool: asyncpg.Connection) -> None:
    """Après 0013 : `upload_media_type` et `upload_s3_key` ont disparu de source_items."""
    await _apply(pool, "0013_drop_upload_intake.sql")

    source_items_cols = await _columns(pool, "source_items")

    assert "upload_media_type" not in source_items_cols
    assert "upload_s3_key" not in source_items_cols


async def test_migration_0013_drops_awaiting_upload_partial_index(
    pool: asyncpg.Connection,
) -> None:
    """L'index partiel du nettoyage périodique des slots upload a disparu."""
    await _apply(pool, "0013_drop_upload_intake.sql")

    indexdef = await pool.fetchval(
        "SELECT indexdef FROM pg_indexes WHERE indexname = 'source_items_awaiting_upload_idx'"
    )
    assert indexdef is None


async def test_migration_0013_replays_on_existing_database_with_upload_rows(
    pool: asyncpg.Connection,
) -> None:
    """Une base portant déjà des lignes issues du cycle upload rejoue sans erreur."""
    source_id = await _insert_source(pool)

    item_id = await pool.fetchval(
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

    await _apply(pool, "0013_drop_upload_intake.sql")

    row = await pool.fetchrow("SELECT * FROM source_items WHERE id = $1", item_id)
    assert "upload_media_type" not in row
    assert "upload_s3_key" not in row


async def test_migration_0013_keeps_scrape_items_unaffected(pool: asyncpg.Connection) -> None:
    """Les items scrape (jamais touchés par upload_*) traversent 0013 sans surprise."""
    source_id = await _insert_source(pool)

    item_id = await pool.fetchval(
        """
        INSERT INTO source_items
            (source_id, tenant_id, platform_item_id, status)
        VALUES ($1, $2, 'vid-42', 'pending_download')
        RETURNING id
        """,
        source_id,
        TENANT_ID,
    )

    await _apply(pool, "0013_drop_upload_intake.sql")

    row = await pool.fetchrow("SELECT * FROM source_items WHERE id = $1", item_id)
    assert row["id"] == item_id
    assert row["status"] == "pending_download"
