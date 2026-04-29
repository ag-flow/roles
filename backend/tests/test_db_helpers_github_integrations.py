"""Tests TDD pour db_helpers/github_integrations.py (Sprint 8)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchrow_return: Any = None
        self.execute_return: str = "INSERT 0 1"

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

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


async def test_upsert_uses_on_conflict_user_id(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """upsert envoie un INSERT...ON CONFLICT (user_id) DO UPDATE — 1 GitHub par user."""
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    tenant_id = uuid4()

    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login="alice",
        github_user_id=12345,
        openbao_path=f"github-tokens/{tenant_id}/{user_id}",
        scope="public_repo",
        pool=stub_pool,
    )
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO github_integrations" in query
    assert "ON CONFLICT (user_id) DO UPDATE" in query
    # Args : tenant_id, user_id, github_login, github_user_id, openbao_path,
    #        scope, last_validated_at
    assert args[0] == tenant_id
    assert args[1] == user_id
    assert args[2] == "alice"
    assert args[3] == 12345
    assert args[5] == "public_repo"
    assert isinstance(args[6], datetime)


async def test_get_by_user_id_returns_dict_when_present(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    stub_conn.fetchrow_return = {
        "id": uuid4(),
        "user_id": user_id,
        "tenant_id": uuid4(),
        "github_login": "alice",
        "github_user_id": 12345,
        "openbao_path": "github-tokens/x/y",
        "scope": "public_repo",
        "last_validated_at": datetime.now(tz=UTC),
        "created_at": datetime.now(tz=UTC),
    }
    result = await github_integrations.get_by_user_id(user_id, pool=stub_pool)
    assert result is not None
    assert result["github_login"] == "alice"
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM github_integrations" in query
    assert args == (user_id,)


async def test_get_by_user_id_none_when_absent(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    stub_conn.fetchrow_return = None
    result = await github_integrations.get_by_user_id(uuid4(), pool=stub_pool)
    assert result is None


async def test_delete_by_user_id_returns_count(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    stub_conn.execute_return = "DELETE 1"
    count = await github_integrations.delete_by_user_id(uuid4(), pool=stub_pool)
    assert count == 1
    method, query, _ = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM github_integrations" in query
