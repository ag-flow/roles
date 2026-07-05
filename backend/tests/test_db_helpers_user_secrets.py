"""Tests pour db_helpers.user_secrets (CRUD secrets utilisateur local/wallet)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from role_builder.db_helpers import user_secrets as helper

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (pattern test_db_helpers_credentials)
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "DELETE 1"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


# ---------------------------------------------------------------------------
# insert_secret — variante locale et variante wallet
# ---------------------------------------------------------------------------


async def test_insert_local_secret(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id = uuid4()
    stub_conn.fetchval_return = secret_id

    result = await helper.insert_secret(
        secret_id=secret_id,
        tenant_id=uuid4(),
        user_id=uuid4(),
        secret_type="openai-whisper",
        label="Ma clé OpenAI",
        storage="local",
        value_encrypted=b"fernet-token",
        wallet_id=None,
        wallet_path=None,
        pool=stub_pool,
    )

    assert result == secret_id
    kind, query, args = stub_conn.calls[0]
    assert kind == "fetchval"
    assert "INSERT INTO user_secrets" in query
    assert b"fernet-token" in args
    assert secret_id in args


async def test_insert_wallet_secret(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id, wallet_id = uuid4(), uuid4()
    stub_conn.fetchval_return = secret_id

    result = await helper.insert_secret(
        secret_id=secret_id,
        tenant_id=uuid4(),
        user_id=uuid4(),
        secret_type="deepgram",
        label="Clé Deepgram",
        storage="wallet",
        value_encrypted=None,
        wallet_id=wallet_id,
        wallet_path="roles/deepgram/abc",
        pool=stub_pool,
    )

    assert result == secret_id
    _, _, args = stub_conn.calls[0]
    assert wallet_id in args
    assert "roles/deepgram/abc" in args


# ---------------------------------------------------------------------------
# list_secrets — jamais les valeurs, filtre optionnel par type
# ---------------------------------------------------------------------------


async def test_list_secrets_excludes_encrypted_values(
    stub_pool: Any, stub_conn: _StubConn
) -> None:
    user_id = uuid4()
    stub_conn.fetch_return = []

    await helper.list_secrets(user_id=user_id, pool=stub_pool)

    _, query, args = stub_conn.calls[0]
    assert "value_encrypted" not in query
    assert "SELECT *" not in query
    assert "user_id = $1" in query
    assert user_id in args


async def test_list_secrets_filters_by_type(stub_pool: Any, stub_conn: _StubConn) -> None:
    user_id = uuid4()

    await helper.list_secrets(user_id=user_id, secret_type="deepgram", pool=stub_pool)

    _, query, args = stub_conn.calls[0]
    assert "secret_type" in query
    assert "deepgram" in args


# ---------------------------------------------------------------------------
# get_secret — scoping user, valeur chiffrée incluse (usage interne store)
# ---------------------------------------------------------------------------


async def test_get_secret_scopes_by_user(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = {"id": secret_id, "storage": "local"}

    row = await helper.get_secret(secret_id=secret_id, user_id=user_id, pool=stub_pool)

    assert row is not None
    _, query, args = stub_conn.calls[0]
    assert "FROM user_secrets" in query
    assert secret_id in args
    assert user_id in args


# ---------------------------------------------------------------------------
# delete_secret / update_secret_status
# ---------------------------------------------------------------------------


async def test_delete_secret(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id, user_id = uuid4(), uuid4()
    stub_conn.execute_return = "DELETE 1"

    deleted = await helper.delete_secret(
        secret_id=secret_id, user_id=user_id, pool=stub_pool
    )

    assert deleted is True
    _, query, args = stub_conn.calls[0]
    assert "DELETE FROM user_secrets" in query
    assert secret_id in args
    assert user_id in args


async def test_update_secret_status(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id = uuid4()

    await helper.update_secret_status(
        secret_id=secret_id, status="invalid", pool=stub_pool
    )

    _, query, args = stub_conn.calls[0]
    assert "UPDATE user_secrets" in query
    assert "status" in query
    assert "invalid" in args


# ---------------------------------------------------------------------------
# count_service_references — garde-fou avant suppression d'un secret
# ---------------------------------------------------------------------------


async def test_count_service_references(stub_pool: Any, stub_conn: _StubConn) -> None:
    secret_id = uuid4()
    stub_conn.fetchval_return = 2

    count = await helper.count_service_references(secret_id=secret_id, pool=stub_pool)

    assert count == 2
    _, query, args = stub_conn.calls[0]
    assert "user_transcription_keys" in query
    assert "user_credentials" in query
    assert secret_id in args
