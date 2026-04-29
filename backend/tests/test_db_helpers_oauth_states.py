"""Tests TDD pour db_helpers/oauth_states.py (Sprint 8)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
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


# ---------------------------------------------------------------------------
# insert_state
# ---------------------------------------------------------------------------


async def test_insert_state_inserts_with_expires_at_aware(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """insert_state passe state, user_id, tenant_id, provider, expires_at (timezone-aware)."""
    from role_builder.db_helpers import oauth_states

    user_id = uuid4()
    tenant_id = uuid4()

    await oauth_states.insert_state(
        state="abc123",
        user_id=user_id,
        tenant_id=tenant_id,
        ttl_seconds=600,
        pool=stub_pool,
    )

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO oauth_states" in query
    # state, user_id, tenant_id, provider, expires_at
    assert args[0] == "abc123"
    assert args[1] == user_id
    assert args[2] == tenant_id
    assert args[3] == "github"
    expires_at = args[4]
    assert isinstance(expires_at, datetime)
    assert expires_at.tzinfo is not None
    delta = expires_at - datetime.now(tz=timezone.utc)
    assert 595 < delta.total_seconds() < 605


async def test_insert_state_accepts_custom_provider(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import oauth_states

    await oauth_states.insert_state(
        state="x",
        user_id=uuid4(),
        tenant_id=uuid4(),
        ttl_seconds=60,
        provider="gitlab",
        pool=stub_pool,
    )
    args = stub_conn.calls[0][2]
    assert args[3] == "gitlab"


# ---------------------------------------------------------------------------
# consume_state
# ---------------------------------------------------------------------------


async def test_consume_state_returns_user_id_when_valid(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """consume_state utilise DELETE...RETURNING (atomique anti-replay)."""
    from role_builder.db_helpers import oauth_states

    user_id = uuid4()
    tenant_id = uuid4()
    stub_conn.fetchrow_return = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "expires_at": datetime.now(tz=timezone.utc) + timedelta(minutes=5),
    }

    result = await oauth_states.consume_state("abc", pool=stub_pool)

    assert result is not None
    assert result["user_id"] == user_id
    assert result["tenant_id"] == tenant_id
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "DELETE FROM oauth_states" in query
    assert "RETURNING" in query
    assert args == ("abc",)


async def test_consume_state_returns_none_when_unknown(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import oauth_states

    stub_conn.fetchrow_return = None
    result = await oauth_states.consume_state("unknown", pool=stub_pool)
    assert result is None


async def test_consume_state_returns_none_when_expired(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    """Si la row existe mais expires_at est dans le passé, retourne None."""
    from role_builder.db_helpers import oauth_states

    stub_conn.fetchrow_return = {
        "user_id": uuid4(),
        "tenant_id": uuid4(),
        "expires_at": datetime.now(tz=timezone.utc) - timedelta(minutes=1),
    }
    result = await oauth_states.consume_state("expired", pool=stub_pool)
    assert result is None


# ---------------------------------------------------------------------------
# cleanup_expired
# ---------------------------------------------------------------------------


async def test_cleanup_expired_returns_count_from_execute_status(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import oauth_states

    stub_conn.execute_return = "DELETE 5"
    count = await oauth_states.cleanup_expired(pool=stub_pool)
    assert count == 5
    method, query, _ = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM oauth_states" in query
    assert "expires_at < now()" in query


async def test_cleanup_expired_returns_zero_when_unparseable(
    stub_conn: _StubConn, stub_pool: Any,
) -> None:
    from role_builder.db_helpers import oauth_states

    stub_conn.execute_return = ""
    count = await oauth_states.cleanup_expired(pool=stub_pool)
    assert count == 0
