"""Fixture Postgres éphémère (migrations 0001..0007 appliquées) pour les tests
d'intégration de services.acquisition.* — même pattern que
test_migration_0005_0006.py, mais expose un vrai `asyncpg.Pool` (les
db_helpers attendent tous `pool: asyncpg.Pool`, pas une connexion nue).
"""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[4] / "migrations"

ADMIN_DSN = os.environ.get(
    "TEST_DATABASE_ADMIN_URL",
    "postgresql://rb:changeme_in_real_env@localhost:5432/postgres",
)

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
    """Pool asyncpg sur une base éphémère fraîche, schéma complet, détruite en fin de test."""
    if not await _postgres_reachable():
        pytest.skip(f"Postgres non joignable via TEST_DATABASE_ADMIN_URL ({ADMIN_DSN})")

    db_name = f"rb_svctest_{uuid.uuid4().hex[:12]}"
    admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
    try:
        await admin_conn.execute(f'CREATE DATABASE "{db_name}"')
    finally:
        await admin_conn.close()

    target_dsn = re.sub(r"/[^/]+$", f"/{db_name}", ADMIN_DSN)

    setup_conn = await asyncpg.connect(dsn=target_dsn)
    try:
        for filename in ALL_MIGRATIONS:
            sql = (MIGRATIONS_DIR / filename).read_text(encoding="utf-8")
            await setup_conn.execute(sql)
    finally:
        await setup_conn.close()

    created_pool = await asyncpg.create_pool(dsn=target_dsn, min_size=1, max_size=5)
    try:
        yield created_pool
    finally:
        await created_pool.close()
        admin_conn = await asyncpg.connect(dsn=ADMIN_DSN)
        try:
            await admin_conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')
        finally:
            await admin_conn.close()


TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def insert_active_credential(
    pool: asyncpg.Pool, *, platform: str, user_id: uuid.UUID | None = None
) -> uuid.UUID:
    """Helper de fixture : crée une user_credentials active (avec son secret cookies)."""
    from role_builder.db_helpers import credentials as credentials_helper
    from role_builder.db_helpers import user_secrets as secrets_helper

    owner_id = user_id or uuid.uuid4()
    secret_id = await secrets_helper.insert_secret(
        secret_id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        user_id=owner_id,
        secret_type=f"{platform}-cookies",
        label="test",
        storage="local",
        value_encrypted=b"stub",
        wallet_id=None,
        wallet_path=None,
        pool=pool,
    )
    return await credentials_helper.insert_user_credential(
        tenant_id=TENANT_ID,
        user_id=owner_id,
        platform=platform,
        label="test",
        secret_id=secret_id,
        status="active",
        pool=pool,
    )
