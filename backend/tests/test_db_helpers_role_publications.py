"""Tests TDD pour db_helpers/role_publications.py (Sprint 8)."""

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

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return


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


async def test_insert_returns_id_and_published_at(
    stub_conn: _StubConn,
    stub_pool: Any,
) -> None:
    from role_builder.db_helpers import role_publications

    pub_id = uuid4()
    now = datetime.now(tz=UTC)
    stub_conn.fetchrow_return = {"id": pub_id, "published_at": now}

    result = await role_publications.insert(
        role_project_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        commit_sha="abc123",
        files_count=5,
        summary="Pushed",
        pool=stub_pool,
    )
    assert result["id"] == pub_id
    assert result["published_at"] == now
    method, query, _ = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "INSERT INTO role_publications" in query
    assert "RETURNING" in query


async def test_list_by_project_query_order_desc_with_limit(
    stub_conn: _StubConn,
    stub_pool: Any,
) -> None:
    from role_builder.db_helpers import role_publications

    project_id = uuid4()
    stub_conn.fetch_return = []
    await role_publications.list_by_project(project_id, limit=20, pool=stub_pool)
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY published_at DESC" in query
    assert "LIMIT $2" in query
    assert args == (project_id, 20)


async def test_get_latest_returns_dict_or_none(
    stub_conn: _StubConn,
    stub_pool: Any,
) -> None:
    from role_builder.db_helpers import role_publications

    project_id = uuid4()
    stub_conn.fetchrow_return = None
    result = await role_publications.get_latest(project_id, pool=stub_pool)
    assert result is None

    now = datetime.now(tz=UTC)
    stub_conn.calls.clear()
    stub_conn.fetchrow_return = {"published_at": now, "commit_sha": "abc"}
    result = await role_publications.get_latest(project_id, pool=stub_pool)
    assert result is not None
    assert result["commit_sha"] == "abc"
