"""Test d'intégration de la migration 0009 (wallets + secrets utilisateur).

Même pattern que test_migration_0008.py : Postgres réel éphémère,
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
    """Connexion à une base éphémère fraîche (migrations 0001..0008), détruite en fin de test."""
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


async def _insert_wallet(db: asyncpg.Connection, user_id: uuid.UUID) -> uuid.UUID:
    return await db.fetchval(
        """
        INSERT INTO user_wallets (tenant_id, user_id, label, api_token_encrypted)
        VALUES ($1, $2, 'perso', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        b"encrypted",
    )


async def test_0009_local_secret_roundtrip(db: asyncpg.Connection) -> None:
    """Un secret local porte une valeur chiffrée, sans wallet."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    secret_id = await db.fetchval(
        """
        INSERT INTO user_secrets
            (tenant_id, user_id, secret_type, label, storage, value_encrypted)
        VALUES ($1, $2, 'openai-whisper', 'Ma clé', 'local', $3)
        RETURNING id
        """,
        TENANT_ID,
        uuid.uuid4(),
        b"fernet-token",
    )
    row = await db.fetchrow("SELECT * FROM user_secrets WHERE id = $1", secret_id)
    assert row["storage"] == "local"
    assert bytes(row["value_encrypted"]) == b"fernet-token"
    assert row["wallet_id"] is None


async def test_0009_wallet_secret_roundtrip(db: asyncpg.Connection) -> None:
    """Un secret wallet porte wallet_id + wallet_path, sans valeur."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    user_id = uuid.uuid4()
    wallet_id = await _insert_wallet(db, user_id)
    assert wallet_id is not None

    secret_id = await db.fetchval(
        """
        INSERT INTO user_secrets
            (tenant_id, user_id, secret_type, label, storage, wallet_id, wallet_path)
        VALUES ($1, $2, 'deepgram', 'Clé DG', 'wallet', $3, 'roles/deepgram/abc')
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        wallet_id,
    )
    row = await db.fetchrow("SELECT * FROM user_secrets WHERE id = $1", secret_id)
    assert row["wallet_path"] == "roles/deepgram/abc"
    assert row["value_encrypted"] is None


async def test_0009_storage_shape_constraint(db: asyncpg.Connection) -> None:
    """Le CHECK refuse les formes incohérentes (local avec wallet, wallet sans path…)."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    user_id = uuid.uuid4()
    wallet_id = await _insert_wallet(db, user_id)

    # local avec wallet_id → rejeté
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            """
            INSERT INTO user_secrets
                (tenant_id, user_id, secret_type, label, storage,
                 value_encrypted, wallet_id, wallet_path)
            VALUES ($1, $2, 'deepgram', 'x', 'local', $3, $4, 'p')
            """,
            TENANT_ID,
            user_id,
            b"v",
            wallet_id,
        )

    # wallet sans path → rejeté
    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            """
            INSERT INTO user_secrets
                (tenant_id, user_id, secret_type, label, storage, wallet_id)
            VALUES ($1, $2, 'deepgram', 'x', 'wallet', $3)
            """,
            TENANT_ID,
            user_id,
            wallet_id,
        )


async def test_0009_secret_type_enum_enforced(db: asyncpg.Connection) -> None:
    """Le CHECK sur secret_type refuse un type hors enum."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    with pytest.raises(asyncpg.CheckViolationError):
        await db.execute(
            """
            INSERT INTO user_secrets
                (tenant_id, user_id, secret_type, label, storage, value_encrypted)
            VALUES ($1, $2, 'mistral', 'x', 'local', $3)
            """,
            TENANT_ID,
            uuid.uuid4(),
            b"v",
        )


async def test_0009_wallet_delete_restricted_by_secrets(db: asyncpg.Connection) -> None:
    """Un wallet référencé par un secret ne peut pas être supprimé (FK RESTRICT)."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    user_id = uuid.uuid4()
    wallet_id = await _insert_wallet(db, user_id)
    await db.execute(
        """
        INSERT INTO user_secrets
            (tenant_id, user_id, secret_type, label, storage, wallet_id, wallet_path)
        VALUES ($1, $2, 'deepgram', 'x', 'wallet', $3, 'roles/deepgram/a')
        """,
        TENANT_ID,
        user_id,
        wallet_id,
    )

    with pytest.raises(asyncpg.RestrictViolationError):
        await db.execute("DELETE FROM user_wallets WHERE id = $1", wallet_id)


async def test_0009_service_tables_gain_secret_id(db: asyncpg.Connection) -> None:
    """user_transcription_keys et user_credentials gagnent secret_id (FK RESTRICT)."""
    await _apply(db, "0009_user_wallets_secrets.sql")

    user_id = uuid.uuid4()
    secret_id = await db.fetchval(
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

    key_id = await db.fetchval(
        """
        INSERT INTO user_transcription_keys
            (tenant_id, user_id, provider, vault_secret_name, status, secret_id)
        VALUES ($1, $2, 'openai-whisper', 'legacy', 'active', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        secret_id,
    )
    assert key_id is not None

    cred_id = await db.fetchval(
        """
        INSERT INTO user_credentials
            (tenant_id, user_id, platform, vault_secret_name, status, secret_id)
        VALUES ($1, $2, 'youtube', 'legacy', 'active', $3)
        RETURNING id
        """,
        TENANT_ID,
        user_id,
        secret_id,
    )
    assert cred_id is not None

    # Le secret référencé ne peut pas être supprimé tant que le service existe
    with pytest.raises(asyncpg.RestrictViolationError):
        await db.execute("DELETE FROM user_secrets WHERE id = $1", secret_id)
