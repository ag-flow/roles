"""Tests pour db_helpers.user_wallets (CRUD wallets Harpocrate par utilisateur)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

from role_builder.db_helpers import user_wallets as helper

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
# insert_wallet
# ---------------------------------------------------------------------------


async def test_insert_wallet_returns_id(stub_pool: Any, stub_conn: _StubConn) -> None:
    wallet_id = uuid4()
    stub_conn.fetchval_return = wallet_id

    result = await helper.insert_wallet(
        tenant_id=uuid4(),
        user_id=uuid4(),
        label="Mon wallet perso",
        api_token_encrypted=b"encrypted-token",
        api_url="https://vault.yoops.org",
        pool=stub_pool,
    )

    assert result == wallet_id
    kind, query, args = stub_conn.calls[0]
    assert kind == "fetchval"
    assert "INSERT INTO user_wallets" in query
    assert b"encrypted-token" in args


# ---------------------------------------------------------------------------
# list_wallets — ordre chronologique (le premier = présélection UI)
# ---------------------------------------------------------------------------


async def test_list_wallets_filters_user_and_orders_asc(
    stub_pool: Any, stub_conn: _StubConn
) -> None:
    user_id = uuid4()
    stub_conn.fetch_return = [{"id": uuid4(), "label": "w1"}]

    rows = await helper.list_wallets(user_id=user_id, pool=stub_pool)

    assert len(rows) == 1
    _, query, args = stub_conn.calls[0]
    assert "FROM user_wallets" in query
    assert "user_id = $1" in query
    assert "ORDER BY created_at" in query
    assert "DESC" not in query
    assert user_id in args


# ---------------------------------------------------------------------------
# get_wallet — scoping par user_id (privé par utilisateur)
# ---------------------------------------------------------------------------


async def test_get_wallet_scopes_by_user(stub_pool: Any, stub_conn: _StubConn) -> None:
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.fetchrow_return = {"id": wallet_id}

    row = await helper.get_wallet(wallet_id=wallet_id, user_id=user_id, pool=stub_pool)

    assert row == {"id": wallet_id}
    _, query, args = stub_conn.calls[0]
    assert "user_id" in query
    assert wallet_id in args
    assert user_id in args


async def test_get_wallet_returns_none_when_absent(
    stub_pool: Any, stub_conn: _StubConn
) -> None:
    stub_conn.fetchrow_return = None
    row = await helper.get_wallet(wallet_id=uuid4(), user_id=uuid4(), pool=stub_pool)
    assert row is None


# ---------------------------------------------------------------------------
# delete_wallet
# ---------------------------------------------------------------------------


async def test_delete_wallet_scopes_by_user(stub_pool: Any, stub_conn: _StubConn) -> None:
    wallet_id, user_id = uuid4(), uuid4()
    stub_conn.execute_return = "DELETE 1"

    deleted = await helper.delete_wallet(
        wallet_id=wallet_id, user_id=user_id, pool=stub_pool
    )

    assert deleted is True
    _, query, args = stub_conn.calls[0]
    assert "DELETE FROM user_wallets" in query
    assert wallet_id in args
    assert user_id in args


async def test_delete_wallet_returns_false_when_absent(
    stub_pool: Any, stub_conn: _StubConn
) -> None:
    stub_conn.execute_return = "DELETE 0"
    deleted = await helper.delete_wallet(
        wallet_id=uuid4(), user_id=uuid4(), pool=stub_pool
    )
    assert deleted is False


# ---------------------------------------------------------------------------
# count_secrets_for_wallet — garde-fou avant suppression (FK RESTRICT)
# ---------------------------------------------------------------------------


async def test_count_secrets_for_wallet(stub_pool: Any, stub_conn: _StubConn) -> None:
    wallet_id = uuid4()
    stub_conn.fetchval_return = 3

    count = await helper.count_secrets_for_wallet(wallet_id=wallet_id, pool=stub_pool)

    assert count == 3
    _, query, args = stub_conn.calls[0]
    assert "FROM user_secrets" in query
    assert wallet_id in args
