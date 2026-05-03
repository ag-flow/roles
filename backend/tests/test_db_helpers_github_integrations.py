"""Tests TDD pour db_helpers/github_integrations.py (Sprint 8 + Phase 2 D)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "INSERT 0 1"

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


async def test_upsert_uses_on_conflict_user_id_github_user_id(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """Phase 2 D — upsert utilise ON CONFLICT (user_id, github_user_id)."""
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    tenant_id = uuid4()

    await github_integrations.upsert(
        user_id=user_id,
        tenant_id=tenant_id,
        github_login="alice",
        github_user_id=12345,
        vault_secret_name=f"github-tokens/{tenant_id}/{user_id}",
        scope="public_repo",
        pool=stub_pool,
    )
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO github_integrations" in query
    assert "ON CONFLICT (user_id, github_user_id) DO UPDATE" in query
    assert args[0] == tenant_id
    assert args[1] == user_id
    assert args[2] == "alice"
    assert args[3] == 12345
    assert args[5] == "public_repo"
    assert isinstance(args[6], datetime)


async def test_get_by_user_id_returns_primary_when_present(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """get_by_user_id retourne la primary (la plus récente)."""
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    stub_conn.fetchrow_return = {
        "id": uuid4(),
        "user_id": user_id,
        "tenant_id": uuid4(),
        "github_login": "alice",
        "github_user_id": 12345,
        "vault_secret_name": "github-tokens/x/y",
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
    assert "ORDER BY last_validated_at DESC NULLS LAST" in query
    assert "LIMIT 1" in query
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

    stub_conn.execute_return = "DELETE 2"
    count = await github_integrations.delete_by_user_id(uuid4(), pool=stub_pool)
    assert count == 2
    method, query, _ = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM github_integrations" in query


# ---------------------------------------------------------------------------
# Phase 2 D : nouveaux helpers
# ---------------------------------------------------------------------------


async def test_list_by_user_id_returns_all_integrations(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    user_id = uuid4()
    now = datetime.now(tz=UTC)
    stub_conn.fetch_return = [
        {
            "id": uuid4(), "user_id": user_id, "tenant_id": uuid4(),
            "github_login": "alice", "github_user_id": 1, "vault_secret_name": "p1",
            "scope": "public_repo", "last_validated_at": now, "created_at": now,
        },
        {
            "id": uuid4(), "user_id": user_id, "tenant_id": uuid4(),
            "github_login": "alice-org", "github_user_id": 2, "vault_secret_name": "p2",
            "scope": "public_repo", "last_validated_at": now, "created_at": now,
        },
    ]
    result = await github_integrations.list_by_user_id(user_id, pool=stub_pool)
    assert len(result) == 2
    assert {r["github_login"] for r in result} == {"alice", "alice-org"}
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY created_at ASC" in query
    assert args == (user_id,)


async def test_get_by_id_returns_dict(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    integration_id = uuid4()
    stub_conn.fetchrow_return = {
        "id": integration_id, "user_id": uuid4(), "tenant_id": uuid4(),
        "github_login": "bob", "github_user_id": 99, "vault_secret_name": "p",
        "scope": "public_repo", "last_validated_at": None,
        "created_at": datetime.now(tz=UTC),
    }
    result = await github_integrations.get_by_id(integration_id, pool=stub_pool)
    assert result is not None
    assert result["github_login"] == "bob"
    _, _, args = stub_conn.calls[0]
    assert args == (integration_id,)


async def test_get_by_id_none_when_absent(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    stub_conn.fetchrow_return = None
    result = await github_integrations.get_by_id(uuid4(), pool=stub_pool)
    assert result is None


async def test_delete_by_id_returns_count(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import github_integrations

    stub_conn.execute_return = "DELETE 1"
    count = await github_integrations.delete_by_id(uuid4(), pool=stub_pool)
    assert count == 1
