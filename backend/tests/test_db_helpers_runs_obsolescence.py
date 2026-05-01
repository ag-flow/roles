"""Tests TDD pour mark_obsolete_for_project / mark_obsolete_for_prompt
(Phase 2 sous-projet C)."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self, execute_tag: str = "UPDATE 0") -> None:
        self.execute_tag = execute_tag
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append((query, args))
        return self.execute_tag


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


@pytest.mark.asyncio
async def test_mark_obsolete_for_project_returns_rowcount() -> None:
    from role_builder.db_helpers.runs import mark_obsolete_for_project

    conn = _StubConn(execute_tag="UPDATE 7")
    pool = _StubPool(conn)
    project_id = uuid4()

    rowcount = await mark_obsolete_for_project(project_id, pool=pool)

    assert rowcount == 7
    assert "is_obsolete = true" in conn.calls[0][0]
    assert "role_project_id = $1" in conn.calls[0][0]
    assert "is_obsolete = false" in conn.calls[0][0]  # idempotent
    assert conn.calls[0][1] == (project_id,)


@pytest.mark.asyncio
async def test_mark_obsolete_for_project_zero_when_no_runs() -> None:
    from role_builder.db_helpers.runs import mark_obsolete_for_project

    conn = _StubConn(execute_tag="UPDATE 0")
    pool = _StubPool(conn)
    rowcount = await mark_obsolete_for_project(uuid4(), pool=pool)
    assert rowcount == 0


@pytest.mark.asyncio
async def test_mark_obsolete_for_prompt_excludes_new_version() -> None:
    from role_builder.db_helpers.runs import mark_obsolete_for_prompt

    conn = _StubConn(execute_tag="UPDATE 3")
    pool = _StubPool(conn)
    prompt_id = uuid4()
    new_version_id = uuid4()

    rowcount = await mark_obsolete_for_prompt(
        prompt_id, except_version_id=new_version_id, pool=pool,
    )

    assert rowcount == 3
    sql, args = conn.calls[0]
    assert "id != $2" in sql
    assert args == (prompt_id, new_version_id)


@pytest.mark.asyncio
async def test_mark_obsolete_for_prompt_returns_zero_on_no_runs() -> None:
    from role_builder.db_helpers.runs import mark_obsolete_for_prompt

    conn = _StubConn(execute_tag="UPDATE 0")
    pool = _StubPool(conn)
    rowcount = await mark_obsolete_for_prompt(
        uuid4(), except_version_id=uuid4(), pool=pool,
    )
    assert rowcount == 0
