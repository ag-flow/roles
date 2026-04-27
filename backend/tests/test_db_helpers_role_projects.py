"""Tests for db_helpers.role_projects — get_user_id_for_project + get_by_id."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return


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


async def test_get_by_id_returns_none_when_not_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_by_id retourne None quand fetchrow retourne None."""
    from role_builder.db_helpers import role_projects

    stub_conn.fetchrow_return = None
    project_id = uuid4()

    result = await role_projects.get_by_id(project_id, pool=stub_pool)

    assert result is None
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM role_projects" in query
    assert "WHERE id = $1" in query
    assert args[0] == project_id


async def test_get_by_id_returns_dict_when_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_by_id retourne dict complet quand la row existe."""
    from role_builder.db_helpers import role_projects

    project_id = uuid4()
    row_data = {
        "id": project_id,
        "display_name": "Mon projet",
        "global_directives": "Directives globales",
        "tenant_id": uuid4(),
    }
    stub_conn.fetchrow_return = row_data

    result = await role_projects.get_by_id(project_id, pool=stub_pool)

    assert result is not None
    assert result["id"] == project_id
    assert result["display_name"] == "Mon projet"
    assert result["global_directives"] == "Directives globales"
