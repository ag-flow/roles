"""Tests for db_helpers.transcription_keys — list active + mark_exhausted/invalid."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> None:
        self.calls.append(("execute", query, args))


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


async def test_list_active_keys_filters_status_active(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_active_keys runs a SELECT WHERE status='active'."""
    from role_builder.db_helpers import transcription_keys

    rows = [
        {"id": uuid4(), "user_id": uuid4(), "provider": "openai-whisper"},
        {"id": uuid4(), "user_id": uuid4(), "provider": "deepgram"},
    ]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_active_keys(pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    # No user_id filter for the global variant
    assert args == ()


async def test_list_active_keys_for_user_filters_user_and_status(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_active_keys_for_user passes user_id arg + filters status='active'."""
    from role_builder.db_helpers import transcription_keys

    user_id = uuid4()
    rows = [{"id": uuid4(), "user_id": user_id, "provider": "openai-whisper"}]
    stub_conn.fetch_return = rows

    result = await transcription_keys.list_active_keys_for_user(user_id, pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM user_transcription_keys" in query
    assert "user_id = $1" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    assert user_id in args


async def test_get_primary_key_returns_row_or_none(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_primary_key picks is_primary=true AND status='active'."""
    from role_builder.db_helpers import transcription_keys

    user_id = uuid4()
    row = {"id": uuid4(), "user_id": user_id, "is_primary": True, "status": "active"}
    stub_conn.fetchrow_return = row

    result = await transcription_keys.get_primary_key(user_id, pool=stub_pool)
    assert result == row

    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM user_transcription_keys" in query
    assert "is_primary = true" in query
    assert "status = 'active'" in query or "status='active'" in query.replace(" ", "")
    assert user_id in args

    # None case
    stub_conn.fetchrow_return = None
    stub_conn.calls.clear()
    result2 = await transcription_keys.get_primary_key(user_id, pool=stub_pool)
    assert result2 is None


async def test_mark_exhausted_updates_status(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """mark_exhausted updates status to 'exhausted'."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.mark_exhausted(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "exhausted" in query
    assert key_id in args


async def test_mark_invalid_updates_status(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """mark_invalid updates status to 'invalid'."""
    from role_builder.db_helpers import transcription_keys

    key_id = uuid4()
    await transcription_keys.mark_invalid(key_id, pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE user_transcription_keys" in query
    assert "invalid" in query
    assert key_id in args
