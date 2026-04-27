"""Tests for db_helpers.runs — create + lifecycle + list."""

from __future__ import annotations

import json
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


async def test_create_run_inserts_pending_returns_uuid(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """create_run envoie INSERT avec status='pending' et retourne UUID via fetchval."""
    from role_builder.db_helpers import runs

    run_id = uuid4()
    stub_conn.fetchval_return = run_id

    result = await runs.create_run(
        role_project_id=uuid4(),
        tenant_id=uuid4(),
        prompt_version_id=uuid4(),
        pool=stub_pool,
    )

    assert result == run_id
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO runs" in query
    assert "pending" in query


async def test_create_run_serializes_input_summary_as_json(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """create_run sérialise input_summary dict en JSON avant INSERT."""
    from role_builder.db_helpers import runs

    stub_conn.fetchval_return = uuid4()
    input_summary = {"chunks_count": 42, "model": "mistral"}

    await runs.create_run(
        role_project_id=uuid4(),
        tenant_id=uuid4(),
        prompt_version_id=uuid4(),
        input_summary=input_summary,
        pool=stub_pool,
    )

    _method, _query, args = stub_conn.calls[0]
    # l'input_summary doit avoir été sérialisé en JSON string dans les args
    json_args = [a for a in args if isinstance(a, str) and "chunks_count" in a]
    assert len(json_args) == 1
    parsed = json.loads(json_args[0])
    assert parsed == input_summary


async def test_mark_running_sends_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_running envoie UPDATE status='running' + started_at=now()."""
    from role_builder.db_helpers import runs

    run_id = uuid4()
    await runs.mark_running(run_id, pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE runs" in query
    assert "running" in query
    assert "started_at" in query
    assert run_id in args


async def test_mark_done_sends_update_with_all_fields(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_done envoie UPDATE avec tous les champs LLM + cost + completed_at."""
    from role_builder.db_helpers import runs

    run_id = uuid4()
    await runs.mark_done(
        run_id,
        output="Generated text",
        llm_provider="mistral",
        llm_model="mistral-large-latest",
        tokens_input=1000,
        tokens_output=500,
        cost_usd=0.005,
        pool=stub_pool,
    )

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE runs" in query
    assert "done" in query
    assert "completed_at" in query
    assert run_id in args
    assert "Generated text" in args
    assert 1000 in args
    assert 500 in args


async def test_mark_failed_sends_update_status_failed(stub_conn: _StubConn, stub_pool: Any) -> None:
    """mark_failed envoie UPDATE status='failed' + error + completed_at."""
    from role_builder.db_helpers import runs

    run_id = uuid4()
    error_msg = "LLM timeout"
    await runs.mark_failed(run_id, error_msg, pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE runs" in query
    assert "failed" in query
    assert "completed_at" in query
    assert run_id in args
    assert error_msg in args


async def test_list_runs_without_status_filter(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_runs sans status ne contient pas 'AND status' dans la query."""
    from role_builder.db_helpers import runs

    project_id = uuid4()
    stub_conn.fetch_return = []

    await runs.list_runs(project_id, pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM runs" in query
    assert "AND status" not in query
    assert project_id in args


async def test_list_runs_with_status_filter_adds_where_clause(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_runs avec status='done' ajoute un filtre AND status dans la query."""
    from role_builder.db_helpers import runs

    project_id = uuid4()
    stub_conn.fetch_return = []

    await runs.list_runs(project_id, status="done", pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "AND status" in query
    assert "done" in args
