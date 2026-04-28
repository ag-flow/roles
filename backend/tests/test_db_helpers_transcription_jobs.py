"""Tests for db_helpers.transcription_jobs — insert + reassign + list."""

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
        self.execute_return: str = "UPDATE 0"

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


async def test_insert_job_returns_uuid(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_job persiste un row pending et retourne l'id généré."""
    from role_builder.db_helpers import transcription_jobs

    new_id = uuid4()
    stub_conn.fetchval_return = new_id

    source_item_id = uuid4()
    tenant_id = uuid4()

    result = await transcription_jobs.insert_job(
        source_item_id=source_item_id,
        tenant_id=tenant_id,
        audio_s3_key="bucket/audio.mp3",
        language="fr",
        worker_pool_id="user_abc",
        priority=2,
        pool=stub_pool,
    )

    assert result == new_id
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO transcription_jobs" in query
    assert "RETURNING id" in query
    # Args contiennent les valeurs critiques
    assert source_item_id in args
    assert tenant_id in args
    assert "bucket/audio.mp3" in args
    assert "fr" in args
    assert "user_abc" in args
    assert 2 in args


async def test_reassign_pending_to_shared_updates_pending_only(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """reassign_pending_to_shared bascule worker_pool_id user_<id> -> shared_default
    pour les jobs status='pending'. Retourne le nombre de lignes modifiées."""
    from role_builder.db_helpers import transcription_jobs

    stub_conn.execute_return = "UPDATE 4"

    n = await transcription_jobs.reassign_pending_to_shared("user_xyz", pool=stub_pool)
    assert n == 4

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE transcription_jobs" in query
    assert "shared_default" in query
    assert "pending" in query
    assert "user_xyz" in args


async def test_list_jobs_optional_filters(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_jobs accepte status et worker_pool_id optionnels + LIMIT."""
    from role_builder.db_helpers import transcription_jobs

    rows = [{"id": uuid4(), "status": "pending"}]
    stub_conn.fetch_return = rows

    # Cas avec les 2 filtres
    result = await transcription_jobs.list_jobs(
        status="pending", worker_pool_id="user_xyz", limit=20, pool=stub_pool
    )
    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM transcription_jobs" in query
    assert "status = $" in query
    assert "worker_pool_id = $" in query
    assert "pending" in args
    assert "user_xyz" in args
    assert 20 in args

    # Cas sans filtre : pas de WHERE
    stub_conn.calls.clear()
    await transcription_jobs.list_jobs(limit=5, pool=stub_pool)
    _, q2, args2 = stub_conn.calls[0]
    assert "WHERE" not in q2
    assert 5 in args2
