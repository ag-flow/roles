"""Tests for db_helpers.role_projects — get_user_id_for_project + list_for_user."""

from __future__ import annotations

from typing import Any
from uuid import uuid4


class _StubConn:
    def __init__(self, fetchval_return: Any = None, fetch_return: list[Any] | None = None) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return = fetchval_return
        self.fetch_return: list[Any] = fetch_return or []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

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


async def test_get_user_id_for_project_found() -> None:
    from role_builder.db_helpers.role_projects import get_user_id_for_project

    role_project_id = uuid4()
    user_id = uuid4()
    conn = _StubConn(fetchval_return=user_id)
    pool = _StubPool(conn)

    result = await get_user_id_for_project(role_project_id, pool=pool)

    assert result == user_id
    _, query, args = conn.calls[0]
    assert "SELECT user_id FROM role_projects WHERE id = $1" in query
    assert args == (role_project_id,)


async def test_get_user_id_for_project_not_found() -> None:
    from role_builder.db_helpers.role_projects import get_user_id_for_project

    conn = _StubConn(fetchval_return=None)
    pool = _StubPool(conn)

    result = await get_user_id_for_project(uuid4(), pool=pool)

    assert result is None


async def test_list_for_user_sends_select_where_user_id() -> None:
    from role_builder.db_helpers.role_projects import list_for_user

    user_id = uuid4()
    row1 = {"id": uuid4(), "user_id": user_id, "display_name": "Projet A"}
    row2 = {"id": uuid4(), "user_id": user_id, "display_name": "Projet B"}
    conn = _StubConn(fetch_return=[row1, row2])
    pool = _StubPool(conn)

    result = await list_for_user(user_id, pool=pool)

    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "fetch"
    assert "WHERE user_id = $1" in query
    assert "ORDER BY created_at DESC" in query
    assert args[0] == user_id

    assert len(result) == 2
    assert result[0]["display_name"] == "Projet A"
    assert result[1]["display_name"] == "Projet B"


async def test_list_for_user_returns_empty_list_when_no_rows() -> None:
    from role_builder.db_helpers.role_projects import list_for_user

    conn = _StubConn(fetch_return=[])
    pool = _StubPool(conn)

    result = await list_for_user(uuid4(), pool=pool)

    assert result == []
