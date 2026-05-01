"""Tests TDD pour role_projects.update_custom_sections (Phase 2 sous-projet G)."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self, execute_tag: str = "UPDATE 1") -> None:
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
async def test_update_custom_sections_serializes_as_json() -> None:
    from role_builder.db_helpers.role_projects import update_custom_sections

    conn = _StubConn(execute_tag="UPDATE 1")
    pool = _StubPool(conn)
    project_id = uuid4()

    await update_custom_sections(
        project_id, ["Outils", "Style-redactionnel"], pool=pool,
    )
    sql, args = conn.calls[0]
    assert "UPDATE role_projects SET custom_sections = $2::jsonb" in sql
    assert args[0] == project_id
    assert json.loads(args[1]) == ["Outils", "Style-redactionnel"]


@pytest.mark.asyncio
async def test_update_custom_sections_accepts_empty_list() -> None:
    from role_builder.db_helpers.role_projects import update_custom_sections

    conn = _StubConn(execute_tag="UPDATE 1")
    pool = _StubPool(conn)
    await update_custom_sections(uuid4(), [], pool=pool)
    _, args = conn.calls[0]
    assert json.loads(args[1]) == []


@pytest.mark.asyncio
async def test_update_custom_sections_raises_when_no_rows() -> None:
    from role_builder.db_helpers.role_projects import update_custom_sections

    conn = _StubConn(execute_tag="UPDATE 0")
    pool = _StubPool(conn)
    with pytest.raises(ValueError, match="not found"):
        await update_custom_sections(uuid4(), ["Outils"], pool=pool)
