"""Tests for db_helpers.clusters — insert + list_by_run/project + delete_by_run."""

from __future__ import annotations

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


async def test_insert_cluster_args_order_and_returns_uuid(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_cluster envoie INSERT avec args correctement ordonnés et retourne UUID."""
    from role_builder.db_helpers import clusters

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    run_id = uuid4()
    project_id = uuid4()
    tenant_id = uuid4()
    sig1 = uuid4()
    sig2 = uuid4()

    result = await clusters.insert_cluster(
        run_id=run_id,
        role_project_id=project_id,
        tenant_id=tenant_id,
        name="Cluster A",
        description="Description du cluster A",
        signal_ids=[sig1, sig2],
        pool=stub_pool,
    )

    assert result == expected_id
    assert len(stub_conn.calls) == 1

    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO clusters" in query
    assert "RETURNING id" in query

    # Vérification ordre : run_id, role_project_id, tenant_id, name, description, signal_ids
    assert args[0] == run_id
    assert args[1] == project_id
    assert args[2] == tenant_id
    assert args[3] == "Cluster A"
    assert args[4] == "Description du cluster A"
    assert args[5] == [sig1, sig2]


async def test_insert_cluster_with_none_description(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_cluster accepte description=None."""
    from role_builder.db_helpers import clusters

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    result = await clusters.insert_cluster(
        run_id=uuid4(),
        role_project_id=uuid4(),
        tenant_id=uuid4(),
        name="Cluster sans description",
        description=None,
        signal_ids=[uuid4()],
        pool=stub_pool,
    )

    assert result == expected_id
    method, query, args = stub_conn.calls[0]
    assert args[4] is None


async def test_list_clusters_by_run_orders_asc(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_clusters_by_run envoie la query avec ORDER BY created_at ASC."""
    from role_builder.db_helpers import clusters

    run_id = uuid4()
    rows = [{"id": uuid4(), "name": "Cluster 1"}, {"id": uuid4(), "name": "Cluster 2"}]
    stub_conn.fetch_return = rows

    result = await clusters.list_clusters_by_run(run_id, pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "WHERE run_id = $1" in query
    assert "ORDER BY created_at ASC" in query
    assert args[0] == run_id


async def test_list_clusters_by_project_orders_desc(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_clusters_by_project envoie la query avec ORDER BY created_at DESC."""
    from role_builder.db_helpers import clusters

    project_id = uuid4()
    rows = [{"id": uuid4(), "name": "Cluster récent"}, {"id": uuid4(), "name": "Cluster ancien"}]
    stub_conn.fetch_return = rows

    result = await clusters.list_clusters_by_project(project_id, pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "WHERE role_project_id = $1" in query
    assert "ORDER BY created_at DESC" in query
    assert args[0] == project_id


async def test_delete_clusters_by_run_parses_count(stub_conn: _StubConn, stub_pool: Any) -> None:
    """delete_clusters_by_run parse 'DELETE N' et retourne int."""
    from role_builder.db_helpers import clusters

    run_id = uuid4()
    stub_conn.execute_return = "DELETE 5"

    count = await clusters.delete_clusters_by_run(run_id, pool=stub_pool)

    assert count == 5
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM clusters WHERE run_id = $1" in query
    assert args[0] == run_id


async def test_delete_clusters_by_run_returns_zero(stub_conn: _StubConn, stub_pool: Any) -> None:
    """delete_clusters_by_run retourne 0 quand aucun cluster supprimé ('DELETE 0')."""
    from role_builder.db_helpers import clusters

    run_id = uuid4()
    stub_conn.execute_return = "DELETE 0"

    count = await clusters.delete_clusters_by_run(run_id, pool=stub_pool)

    assert count == 0
