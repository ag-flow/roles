"""Tests for db_helpers.scraping_jobs — claim FOR UPDATE SKIP LOCKED + lifecycle."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.transaction_count = 0
        self.execute_return: str = "UPDATE 0"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return getattr(self, "fetch_return", [])

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return

    def transaction(self) -> _StubTransaction:
        self.transaction_count += 1
        return _StubTransaction()


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


async def test_insert_job_returns_uuid(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_job returns the new id from RETURNING id."""
    from role_builder.db_helpers import scraping_jobs

    new_id = uuid4()
    stub_conn.fetchval_return = new_id

    source_id = uuid4()
    tenant_id = uuid4()

    returned = await scraping_jobs.insert_job(
        source_id=source_id,
        source_item_id=None,
        tenant_id=tenant_id,
        command="discover",
        priority=5,
        pool=stub_pool,
    )

    assert returned == new_id
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO scraping_jobs" in query
    assert "discover" in args
    assert source_id in args
    assert tenant_id in args
    assert 5 in args


async def test_claim_next_pending_job_returns_none_when_empty(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_pending_job returns None if no pending row found."""
    from role_builder.db_helpers import scraping_jobs

    stub_conn.fetchrow_return = None
    result = await scraping_jobs.claim_next_pending_job("worker-1", pool=stub_pool)
    assert result is None
    # Transaction opened
    assert stub_conn.transaction_count == 1
    # SELECT was called, no UPDATE follow-up
    methods = [c[0] for c in stub_conn.calls]
    assert "fetchrow" in methods
    assert "execute" not in methods


async def test_claim_next_pending_job_updates_when_row_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_pending_job claims the row (UPDATE) and returns the dict."""
    from role_builder.db_helpers import scraping_jobs

    job_id = uuid4()
    job_row = {
        "id": job_id,
        "source_id": uuid4(),
        "command": "discover",
        "tenant_id": uuid4(),
        "priority": 0,
    }
    stub_conn.fetchrow_return = job_row
    result = await scraping_jobs.claim_next_pending_job("worker-1", pool=stub_pool)
    assert result == job_row
    # Both SELECT (fetchrow) and UPDATE (execute) called inside the transaction
    methods = [c[0] for c in stub_conn.calls]
    assert methods == ["fetchrow", "execute"]
    # SELECT FOR UPDATE SKIP LOCKED
    select_query = stub_conn.calls[0][1]
    assert "FOR UPDATE" in select_query
    assert "SKIP LOCKED" in select_query
    assert "pending" in select_query
    # UPDATE sets status=claimed and worker id
    update_query, update_args = stub_conn.calls[1][1], stub_conn.calls[1][2]
    assert "UPDATE scraping_jobs" in update_query
    assert "claimed" in update_query
    assert "worker-1" in update_args
    assert job_id in update_args


async def test_list_jobs_filters_by_status_and_limit(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_jobs forwards status filter (when given) and the LIMIT."""
    from role_builder.db_helpers import scraping_jobs

    rows = [{"id": uuid4(), "status": "pending"}, {"id": uuid4(), "status": "pending"}]
    stub_conn.fetch_return = rows  # type: ignore[attr-defined]

    result = await scraping_jobs.list_jobs(status="pending", limit=10, pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM scraping_jobs" in query
    assert "WHERE status = $1" in query
    assert "ORDER BY created_at DESC" in query
    assert "pending" in args
    assert 10 in args

    # Without status filter, no WHERE clause
    stub_conn.calls.clear()
    await scraping_jobs.list_jobs(limit=5, pool=stub_pool)
    _, query2, args2 = stub_conn.calls[0]
    assert "WHERE" not in query2
    assert 5 in args2


async def test_get_active_job_for_item_returns_true_when_row_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_active_job_for_item — idempotence de select_items (façade MCP)."""
    from role_builder.db_helpers import scraping_jobs

    item_id = uuid4()
    stub_conn.fetchval_return = 1

    found = await scraping_jobs.get_active_job_for_item(item_id, "download", pool=stub_pool)

    assert found is True
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "FROM scraping_jobs" in query
    assert "pending" in query
    assert "claimed" in query
    assert "processing" in query
    assert item_id in args
    assert "download" in args


async def test_get_active_job_for_item_returns_false_when_none(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    from role_builder.db_helpers import scraping_jobs

    stub_conn.fetchval_return = None

    found = await scraping_jobs.get_active_job_for_item(uuid4(), "download", pool=stub_pool)

    assert found is False


async def test_cancel_pending_claimed_returns_count(stub_conn: _StubConn, stub_pool: Any) -> None:
    """cancel_pending_claimed annule pending/claimed d'une source, retourne le compte."""
    from role_builder.db_helpers import scraping_jobs

    stub_conn.execute_return = "UPDATE 3"  # type: ignore[attr-defined]

    source_id = uuid4()
    n = await scraping_jobs.cancel_pending_claimed(source_id, pool=stub_pool)

    assert n == 3
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE scraping_jobs" in query
    assert "cancelled" in query
    assert "pending" in query
    assert "claimed" in query
    assert source_id in args


async def test_mark_job_lifecycle(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_job_processing / mark_job_done / mark_job_failed each issue UPDATE."""
    from role_builder.db_helpers import scraping_jobs

    job_id = uuid4()
    await scraping_jobs.mark_job_processing(job_id, pool=stub_pool)
    await scraping_jobs.mark_job_done(job_id, pool=stub_pool)
    await scraping_jobs.mark_job_failed(job_id, "boom", pool=stub_pool)

    methods = [c[0] for c in stub_conn.calls]
    queries = [c[1] for c in stub_conn.calls]
    assert methods == ["execute", "execute", "execute"]
    assert "processing" in queries[0]
    assert "done" in queries[1]
    assert "failed" in queries[2]
    # Last call carries the error message
    assert "boom" in stub_conn.calls[2][2]
    assert job_id in stub_conn.calls[2][2]
