"""Tests for db_helpers.sources — asyncpg CRUD on the sources table."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetch_return: list[Any] = []
        self.fetchrow_return: Any = None

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

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


async def test_insert_source_returns_uuid(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_source acquires conn, calls INSERT INTO sources, returns the UUID."""
    from role_builder.db_helpers import sources

    new_id = uuid4()
    stub_conn.fetchval_return = new_id

    tenant_id = uuid4()
    returned = await sources.insert_source(
        tenant_id=tenant_id,
        platform="youtube",
        source_type="channel",
        url="https://www.youtube.com/@example",
        pool=stub_pool,
    )

    assert returned == new_id
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO sources" in query
    assert "role_project_id" not in query  # concept retiré (migration 0011)
    # args ordered as in the SQL placeholders
    assert tenant_id in args
    assert "youtube" in args
    assert "channel" in args
    assert "https://www.youtube.com/@example" in args


async def test_update_source_status_executes_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_source_status executes UPDATE sources SET status with optional fields."""
    from role_builder.db_helpers import sources

    source_id = uuid4()
    await sources.update_source_status(
        source_id,
        "discovered",
        discovered_count=42,
        pool=stub_pool,
    )

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE sources" in query
    assert "status" in query
    assert "discovered" in args
    assert 42 in args
    assert source_id in args


async def test_get_source_returns_dict_or_none(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_source returns dict on hit and None on miss."""
    from role_builder.db_helpers import sources

    source_id = uuid4()
    stub_conn.fetchrow_return = {"id": source_id, "platform": "youtube"}

    row = await sources.get_source(source_id, pool=stub_pool)
    assert row == {"id": source_id, "platform": "youtube"}

    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "SELECT" in query
    assert "sources" in query
    assert source_id in args

    # Miss
    stub_conn.fetchrow_return = None
    other = uuid4()
    row2 = await sources.get_source(other, pool=stub_pool)
    assert row2 is None




# silence ruff: parameter present so caller can type-check the UUID-like return
def _silence_uuid_unused() -> UUID:
    return uuid4()
