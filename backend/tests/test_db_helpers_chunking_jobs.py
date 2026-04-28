"""Tests for db_helpers.chunking_jobs — claim FOR UPDATE SKIP LOCKED + lifecycle."""

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
        self.fetch_return: list[Any] = []
        self.transaction_count = 0

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
    """insert_job persiste un row pending et retourne l'id généré."""
    from role_builder.db_helpers import chunking_jobs

    new_id = uuid4()
    stub_conn.fetchval_return = new_id

    item_id = uuid4()
    project_id = uuid4()
    tenant_id = uuid4()

    result = await chunking_jobs.insert_job(
        source_item_id=item_id,
        role_project_id=project_id,
        tenant_id=tenant_id,
        transcript_s3_key="corpus-transcripts/x.json",
        pool=stub_pool,
    )

    assert result == new_id
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO chunking_jobs" in query
    assert "RETURNING id" in query
    assert item_id in args
    assert project_id in args
    assert tenant_id in args
    assert "corpus-transcripts/x.json" in args


async def test_claim_next_pending_job_returns_none_when_empty(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_pending_job retourne None si aucun job pending."""
    from role_builder.db_helpers import chunking_jobs

    stub_conn.fetchrow_return = None
    result = await chunking_jobs.claim_next_pending_job("chunking-worker-1", pool=stub_pool)
    assert result is None
    assert stub_conn.transaction_count == 1
    methods = [c[0] for c in stub_conn.calls]
    assert "fetchrow" in methods
    assert "execute" not in methods


async def test_claim_next_pending_job_updates_when_row_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_pending_job claim la row (UPDATE) et retourne le dict."""
    from role_builder.db_helpers import chunking_jobs

    job_id = uuid4()
    job_row = {
        "id": job_id,
        "source_item_id": uuid4(),
        "role_project_id": uuid4(),
        "tenant_id": uuid4(),
        "transcript_s3_key": "corpus-transcripts/x.json",
        "attempts": 0,
    }
    stub_conn.fetchrow_return = job_row
    result = await chunking_jobs.claim_next_pending_job("chunking-worker-1", pool=stub_pool)
    assert result == job_row

    methods = [c[0] for c in stub_conn.calls]
    assert methods == ["fetchrow", "execute"]
    select_query = stub_conn.calls[0][1]
    assert "FROM chunking_jobs" in select_query
    assert "FOR UPDATE" in select_query
    assert "SKIP LOCKED" in select_query
    assert "pending" in select_query
    update_query, update_args = stub_conn.calls[1][1], stub_conn.calls[1][2]
    assert "UPDATE chunking_jobs" in update_query
    assert "claimed" in update_query
    assert "chunking-worker-1" in update_args
    assert job_id in update_args


async def test_mark_processing_done_failed_lifecycle(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_processing / mark_done(chunks_produced=N) / mark_failed(error)."""
    from role_builder.db_helpers import chunking_jobs

    job_id = uuid4()
    await chunking_jobs.mark_processing(job_id, pool=stub_pool)
    await chunking_jobs.mark_done(job_id, chunks_produced=12, pool=stub_pool)
    await chunking_jobs.mark_failed(job_id, "boom", pool=stub_pool)

    methods = [c[0] for c in stub_conn.calls]
    queries = [c[1] for c in stub_conn.calls]
    assert methods == ["execute", "execute", "execute"]
    assert "processing" in queries[0]
    assert "done" in queries[1]
    assert "chunks_produced" in queries[1]
    assert "failed" in queries[2]
    # mark_done args
    assert 12 in stub_conn.calls[1][2]
    # mark_failed args
    assert "boom" in stub_conn.calls[2][2]
    assert job_id in stub_conn.calls[2][2]


async def test_list_jobs_filters_status_and_limit(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_jobs filtre status optionnel + LIMIT."""
    from role_builder.db_helpers import chunking_jobs

    rows = [{"id": uuid4(), "status": "pending"}]
    stub_conn.fetch_return = rows

    result = await chunking_jobs.list_jobs(status="pending", limit=10, pool=stub_pool)
    assert result == rows

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM chunking_jobs" in query
    assert "status = $" in query
    assert "ORDER BY created_at DESC" in query
    assert "pending" in args
    assert 10 in args

    stub_conn.calls.clear()
    await chunking_jobs.list_jobs(limit=5, pool=stub_pool)
    _, q2, args2 = stub_conn.calls[0]
    assert "WHERE" not in q2
    assert 5 in args2
