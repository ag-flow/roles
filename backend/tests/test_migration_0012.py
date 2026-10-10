"""Test d'intégration de la migration 0012 (audio_s3_key -> audio_path).

Même pattern que test_migration_0010.py : Postgres réel éphémère,
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
    """Connexion à une base éphémère fraîche (migrations 0001..0011), détruite en fin de test.

    Nommée `pool` pour reprendre la signature du brief, mais porte en réalité
    une connexion nue (`asyncpg.Connection`) — même pattern que les autres
    tests de migration de ce dépôt (test_migration_0009.py, 0010.py), qui
    n'utilisent pas un vrai `asyncpg.Pool`.
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


async def _insert_source(conn: asyncpg.Connection) -> uuid.UUID:
    return await conn.fetchval(
        """
        INSERT INTO sources (tenant_id, platform, source_type, url)
        VALUES ($1, 'youtube', 'channel', 'https://youtube.com/@clea-ux')
        RETURNING id
        """,
        TENANT_ID,
    )


async def test_migration_0012_renames_audio_s3_key_to_audio_path(
    pool: asyncpg.Connection,
) -> None:
    """Après 0012 : colonnes `audio_path` présentes, `audio_s3_key` absentes, sur les deux tables."""
    await _apply(pool, "0012_audio_path.sql")

    source_items_cols = await _columns(pool, "source_items")
    transcription_jobs_cols = await _columns(pool, "transcription_jobs")

    assert "audio_path" in source_items_cols
    assert "audio_s3_key" not in source_items_cols
    assert "audio_path" in transcription_jobs_cols
    assert "audio_s3_key" not in transcription_jobs_cols


async def test_migration_0012_replays_on_existing_database(pool: asyncpg.Connection) -> None:
    """Une base portant déjà des lignes (ancien nom de colonne) conserve ses valeurs."""
    source_id = await _insert_source(pool)

    item_id = await pool.fetchval(
        """
        INSERT INTO source_items
            (source_id, tenant_id, platform_item_id, status, audio_s3_key)
        VALUES ($1, $2, 'vid-42', 'audio_ready', 'tenant/v2/src/vid-42.mp3')
        RETURNING id
        """,
        source_id,
        TENANT_ID,
    )
    job_id = await pool.fetchval(
        """
        INSERT INTO transcription_jobs
            (source_item_id, tenant_id, audio_s3_key, worker_pool_id, status)
        VALUES ($1, $2, 'tenant/v2/src/vid-42.mp3', 'shared_default', 'pending')
        RETURNING id
        """,
        item_id,
        TENANT_ID,
    )

    await _apply(pool, "0012_audio_path.sql")

    item_row = await pool.fetchrow("SELECT * FROM source_items WHERE id = $1", item_id)
    job_row = await pool.fetchrow("SELECT * FROM transcription_jobs WHERE id = $1", job_id)

    assert item_row["audio_path"] == "tenant/v2/src/vid-42.mp3"
    assert job_row["audio_path"] == "tenant/v2/src/vid-42.mp3"
