"""Test d'intégration : `_handle_item_done` contre un Postgres réel.

`tests/test_event_handlers.py` immobilise entièrement `transcription_jobs.
insert_job` et `source_items.update_source_item_status` avec des doublures
`fake_*(**kwargs)` qui avalent n'importe quel nom d'argument : un renommage de
paramètre (ex. `audio_s3_key` -> `audio_path`, migration 0012) ne les ferait
jamais échouer. Ce fichier appelle les VRAIES fonctions contre une base
éphémère migrée 0001..0012, pour qu'un futur renommage de signature fasse
rougir un test.

Même pattern que test_migration_0012.py : Postgres réel éphémère, skip
proprement si TEST_DATABASE_ADMIN_URL n'est pas joignable.
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

ALL_MIGRATIONS = (
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


@pytest.fixture
async def pool(request: pytest.FixtureRequest) -> AsyncIterator[asyncpg.Pool]:
    """Pool asyncpg réel sur une base éphémère migrée 0001..0012.

    Un vrai `asyncpg.Pool`, pas une connexion nue : les db_helpers appellent
    `pool.acquire()`, et c'est précisément ce chemin qu'on veut exercer sans
    simulation.
    """
    if not await _postgres_reachable():
        pytest.skip(f"Postgres non joignable via TEST_DATABASE_ADMIN_URL ({ADMIN_DSN})")

    db_name = f"rb_ehtest_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    target_dsn = re.sub(r"/[^/]+$", f"/{db_name}", ADMIN_DSN)
    setup_conn = await asyncpg.connect(dsn=target_dsn)
    try:
        for filename in ALL_MIGRATIONS:
            await setup_conn.execute((MIGRATIONS_DIR / filename).read_text(encoding="utf-8"))
    finally:
        await setup_conn.close()

    db_pool = await asyncpg.create_pool(dsn=target_dsn, min_size=1, max_size=2)
    try:
        yield db_pool
    finally:
        await db_pool.close()
        admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


async def _insert_source_and_item(
    db_pool: asyncpg.Pool, platform_item_id: str
) -> tuple[uuid.UUID, uuid.UUID]:
    async with db_pool.acquire() as conn:
        source_id = await conn.fetchval(
            """
            INSERT INTO sources (tenant_id, platform, source_type, url)
            VALUES ($1, 'youtube', 'channel', 'https://youtube.com/@clea-ux')
            RETURNING id
            """,
            TENANT_ID,
        )
        item_id = await conn.fetchval(
            """
            INSERT INTO source_items (source_id, tenant_id, platform_item_id, status)
            VALUES ($1, $2, $3, 'audio_ready')
            RETURNING id
            """,
            source_id,
            TENANT_ID,
            platform_item_id,
        )
    return source_id, item_id


async def test_item_done_event_persists_audio_path(pool: asyncpg.Pool) -> None:
    """`handle_scraper_event('item_done')` écrit `audio_path` via les vraies
    signatures `insert_job`/`update_source_item_status` (lignes 198/214 de
    event_handlers.py). Avec les anciens appels `audio_s3_key=...`, ce test
    échoue : soit le call lève (kwarg inconnu), soit — ici, puisque l'event
    ne porte plus que `audio_path` — l'ancien code ne le reconnaît jamais et
    classe l'item en échec au lieu de `queued_transcription`."""
    from role_builder.services import event_handlers

    source_id, item_id = await _insert_source_and_item(pool, "vid-real-1")
    audio_path = "/mnt/corpus-audio/00000000-0000-0000-0000-000000000001/v2/src/vid-real-1.mp3"
    job = {
        "id": uuid.uuid4(),
        "source_id": source_id,
        "tenant_id": TENANT_ID,
        "command": "download",
    }

    await event_handlers.handle_scraper_event(
        {"type": "item_done", "item_id": "vid-real-1", "audio_path": audio_path},
        job,
        pool=pool,
    )

    async with pool.acquire() as conn:
        item_row = await conn.fetchrow("SELECT * FROM source_items WHERE id = $1", item_id)
        job_row = await conn.fetchrow(
            "SELECT * FROM transcription_jobs WHERE source_item_id = $1", item_id
        )

    assert item_row["status"] == "queued_transcription"
    assert item_row["audio_path"] == audio_path
    assert job_row is not None
    assert job_row["audio_path"] == audio_path
    assert job_row["worker_pool_id"] == "shared_default"
