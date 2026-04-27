"""Tests for db_helpers.signals — insert + list_by_run/project + get_by_ids."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "DELETE 0"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

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


async def test_insert_signal_args_order_and_returns_uuid(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_signal envoie INSERT avec args correctement ordonnés et retourne UUID."""
    from role_builder.db_helpers import signals

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    run_id = uuid4()
    project_id = uuid4()
    tenant_id = uuid4()
    item_id = uuid4()
    chunk1_id = uuid4()
    chunk2_id = uuid4()
    content = {"title": "Heuristique test", "description": "Une règle pratique"}

    result = await signals.insert_signal(
        run_id=run_id,
        role_project_id=project_id,
        tenant_id=tenant_id,
        source_item_id=item_id,
        source_chunks=[chunk1_id, chunk2_id],
        signal_type="heuristique",
        content=content,
        pool=stub_pool,
    )

    assert result == expected_id
    assert len(stub_conn.calls) == 1

    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO signals" in query
    assert "RETURNING id" in query

    # Vérification ordre args : run_id, role_project_id, tenant_id, source_item_id,
    # source_chunks, signal_type, content_json
    assert args[0] == run_id
    assert args[1] == project_id
    assert args[2] == tenant_id
    assert args[3] == item_id
    assert args[4] == [chunk1_id, chunk2_id]
    assert args[5] == "heuristique"
    # content sérialisé en JSON
    parsed = json.loads(args[6])
    assert parsed == content


async def test_list_signals_by_run_orders_asc(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_signals_by_run envoie la query avec ORDER BY created_at ASC."""
    from role_builder.db_helpers import signals

    run_id = uuid4()
    rows = [{"id": uuid4(), "type": "vocab"}, {"id": uuid4(), "type": "anecdote"}]
    stub_conn.fetch_return = rows

    result = await signals.list_signals_by_run(run_id, pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "WHERE run_id = $1" in query
    assert "ORDER BY created_at ASC" in query
    assert args[0] == run_id


async def test_list_signals_by_project_without_type_filter(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_signals_by_project sans type ne contient pas AND type dans la query."""
    from role_builder.db_helpers import signals

    project_id = uuid4()
    rows = [{"id": uuid4(), "type": "heuristique"}]
    stub_conn.fetch_return = rows

    result = await signals.list_signals_by_project(project_id, pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "AND type" not in query
    assert "WHERE role_project_id = $1" in query
    assert args[0] == project_id


async def test_list_signals_by_project_with_type_filter(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_signals_by_project avec type ajoute AND type = $2 dans la query."""
    from role_builder.db_helpers import signals

    project_id = uuid4()
    rows = [{"id": uuid4(), "type": "heuristique"}]
    stub_conn.fetch_return = rows

    result = await signals.list_signals_by_project(project_id, type="heuristique", pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "AND type = $2" in query
    assert args[0] == project_id
    assert args[1] == "heuristique"


async def test_get_signals_by_ids_empty_returns_without_sql(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_signals_by_ids retourne [] si ids vide, sans appel SQL."""
    from role_builder.db_helpers import signals

    result = await signals.get_signals_by_ids([], pool=stub_pool)

    assert result == []
    assert len(stub_conn.calls) == 0


async def test_get_signals_by_ids_with_ids_uses_any(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_signals_by_ids avec ids envoie SELECT avec ANY($1::uuid[])."""
    from role_builder.db_helpers import signals

    id1 = uuid4()
    id2 = uuid4()
    rows = [{"id": id1, "type": "vocab"}, {"id": id2, "type": "cadre"}]
    stub_conn.fetch_return = rows

    result = await signals.get_signals_by_ids([id1, id2], pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ANY($1::uuid[])" in query
    assert args[0] == [id1, id2]


async def test_delete_signals_by_run_uses_correct_query_and_parses_count(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """delete_signals_by_run : query DELETE correcte, retourne le count parsé depuis 'DELETE N'."""
    from role_builder.db_helpers import signals

    run_id = uuid4()
    stub_conn.execute_return = "DELETE 3"

    count = await signals.delete_signals_by_run(run_id, pool=stub_pool)

    assert count == 3
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM signals WHERE run_id = $1" in query
    assert args[0] == run_id


async def test_delete_signals_by_run_returns_zero_when_none_deleted(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """delete_signals_by_run retourne 0 quand aucun signal supprimé ('DELETE 0')."""
    from role_builder.db_helpers import signals

    run_id = uuid4()
    stub_conn.execute_return = "DELETE 0"

    count = await signals.delete_signals_by_run(run_id, pool=stub_pool)

    assert count == 0
