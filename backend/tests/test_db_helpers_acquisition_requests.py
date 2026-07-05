"""Tests for db_helpers.acquisition_requests — CRUD sur la table acquisition_requests."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import asyncpg
import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchval_side_effect: Exception | None = None
        self.fetch_return: list[Any] = []
        self.fetchrow_return: Any = None

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        if self.fetchval_side_effect is not None:
            raise self.fetchval_side_effect
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


async def test_insert_request_returns_new_id(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_request insère et retourne l'id généré."""
    from role_builder.db_helpers import acquisition_requests as ar

    new_id = uuid4()
    stub_conn.fetchval_return = new_id
    source_id = uuid4()
    tenant_id = uuid4()

    result = await ar.insert_request(
        request_key="yt-clea-ux-2026-07-05-a3f2",
        tenant_id=tenant_id,
        submitted_by="claude-web",
        kind="scrape",
        source_id=source_id,
        mode="discover_only",
        filters=None,
        docflow_target=None,
        note="corpus UX",
        status="discovering",
        pool=stub_pool,
    )

    assert result == new_id
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO acquisition_requests" in query
    assert "yt-clea-ux-2026-07-05-a3f2" in args
    assert "discovering" in args


async def test_insert_request_serializes_filters_to_json(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """filters/docflow_target sont sérialisés en JSON avant insertion (jsonb via cast SQL)."""
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetchval_return = uuid4()

    await ar.insert_request(
        request_key="yt-auto-2026-07-05-b7e1",
        tenant_id=uuid4(),
        submitted_by="claude-web",
        kind="scrape",
        source_id=uuid4(),
        mode="auto",
        filters={"max_items": 10},
        docflow_target={"workspace": "roles"},
        note=None,
        status="discovering",
        pool=stub_pool,
    )

    _, _, args = stub_conn.calls[0]
    assert '{"max_items": 10}' in args
    assert '{"workspace": "roles"}' in args


async def test_insert_request_propagates_unique_violation(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """Une collision de request_key propage UniqueViolationError (retry côté service)."""
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetchval_side_effect = asyncpg.UniqueViolationError("duplicate key")

    with pytest.raises(asyncpg.UniqueViolationError):
        await ar.insert_request(
            request_key="dup-key",
            tenant_id=uuid4(),
            submitted_by="claude-web",
            kind="scrape",
            source_id=uuid4(),
            mode="discover_only",
            filters=None,
            docflow_target=None,
            note=None,
            status="discovering",
            pool=stub_pool,
        )


async def test_get_by_key_returns_row(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_by_key retourne la ligne correspondante, None si absente."""
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetchrow_return = {"request_key": "yt-clea-ux-2026-07-05-a3f2", "status": "discovering"}

    row = await ar.get_by_key("yt-clea-ux-2026-07-05-a3f2", pool=stub_pool)

    assert row is not None
    assert row["request_key"] == "yt-clea-ux-2026-07-05-a3f2"
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM acquisition_requests" in query
    assert "request_key" in query
    assert "yt-clea-ux-2026-07-05-a3f2" in args


async def test_get_by_key_returns_none_when_missing(stub_conn: _StubConn, stub_pool: Any) -> None:
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetchrow_return = None

    row = await ar.get_by_key("unknown", pool=stub_pool)

    assert row is None


async def test_get_by_source_id_returns_row(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_by_source_id — utilisé par event_handlers pour retrouver la requête d'une source."""
    from role_builder.db_helpers import acquisition_requests as ar

    source_id = uuid4()
    stub_conn.fetchrow_return = {"source_id": source_id, "mode": "auto"}

    row = await ar.get_by_source_id(source_id, pool=stub_pool)

    assert row is not None
    assert row["mode"] == "auto"
    _, query, args = stub_conn.calls[0]
    assert "source_id" in query
    assert source_id in args


async def test_update_status_executes_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_status écrit le nouveau statut + touche updated_at."""
    from role_builder.db_helpers import acquisition_requests as ar

    await ar.update_status("yt-clea-ux-2026-07-05-a3f2", "acquiring", pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE acquisition_requests" in query
    assert "acquiring" in args
    assert "yt-clea-ux-2026-07-05-a3f2" in args


async def test_list_requests_applies_filters(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_requests filtre par status et submitted_by quand fournis."""
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetch_return = [{"request_key": "a"}]

    rows = await ar.list_requests(status="discovering", submitted_by="claude-web", pool=stub_pool)

    assert rows == [{"request_key": "a"}]
    _, query, args = stub_conn.calls[0]
    assert "status" in query
    assert "submitted_by" in query
    assert "discovering" in args
    assert "claude-web" in args


async def test_list_requests_without_filters(stub_conn: _StubConn, stub_pool: Any) -> None:
    """Sans filtre, list_requests retourne tout (ordonné par created_at desc)."""
    from role_builder.db_helpers import acquisition_requests as ar

    stub_conn.fetch_return = []

    rows = await ar.list_requests(pool=stub_pool)

    assert rows == []
    _, query, _args = stub_conn.calls[0]
    assert "FROM acquisition_requests" in query
    assert "ORDER BY created_at DESC" in query
