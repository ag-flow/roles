"""Tests for db_helpers.prompts — CRUD prompts + versions + system_default management."""

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


async def test_upsert_prompt_returns_uuid(stub_conn: _StubConn, stub_pool: Any) -> None:
    """upsert_prompt envoie INSERT...ON CONFLICT et retourne UUID via fetchval."""
    from role_builder.db_helpers import prompts

    expected_id = uuid4()
    stub_conn.fetchval_return = expected_id

    result = await prompts.upsert_prompt(
        name="extractor",
        type="extractor",
        target_section=None,
        description="desc",
        pool=stub_pool,
    )

    assert result == expected_id
    assert len(stub_conn.calls) == 1
    method, query, _args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO prompts" in query
    assert "ON CONFLICT" in query
    assert "RETURNING id" in query


async def test_get_prompt_by_name_returns_none_when_absent(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_prompt_by_name retourne None si fetchrow retourne None."""
    from role_builder.db_helpers import prompts

    stub_conn.fetchrow_return = None

    result = await prompts.get_prompt_by_name("extractor", pool=stub_pool)

    assert result is None
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM prompts" in query
    assert "extractor" in args


async def test_get_prompt_by_name_returns_dict_when_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_prompt_by_name retourne dict si fetchrow retourne une row."""
    from role_builder.db_helpers import prompts

    row_data = {"id": uuid4(), "name": "extractor", "type": "extractor"}
    stub_conn.fetchrow_return = row_data

    result = await prompts.get_prompt_by_name("extractor", pool=stub_pool)

    assert result == row_data


async def test_insert_prompt_version_no_system_default_only_insert(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_prompt_version avec is_system_default=False n'envoie qu'un INSERT."""
    from role_builder.db_helpers import prompts

    prompt_id = uuid4()
    version_id = uuid4()
    stub_conn.fetchval_return = version_id

    result = await prompts.insert_prompt_version(
        prompt_id=prompt_id,
        version_number=1,
        template="Tu es un analyste...",
        is_system_default=False,
        pool=stub_pool,
    )

    assert result == version_id
    # Un seul appel : l'INSERT
    assert len(stub_conn.calls) == 1
    method, query, _args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "INSERT INTO prompt_versions" in query


async def test_insert_prompt_version_with_system_default_updates_then_inserts(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_prompt_version is_system_default=True : UPDATE désactive l'ancien, puis INSERT."""
    from role_builder.db_helpers import prompts

    prompt_id = uuid4()
    version_id = uuid4()
    stub_conn.fetchval_return = version_id

    await prompts.insert_prompt_version(
        prompt_id=prompt_id,
        version_number=2,
        template="Nouveau template",
        is_system_default=True,
        pool=stub_pool,
    )

    # 2 appels : UPDATE puis INSERT (fetchval)
    assert len(stub_conn.calls) == 2
    first_method, first_query, first_args = stub_conn.calls[0]
    assert first_method == "execute"
    assert "UPDATE prompt_versions" in first_query
    assert "is_system_default" in first_query
    assert prompt_id in first_args

    second_method, second_query, _args = stub_conn.calls[1]
    assert second_method == "fetchval"
    assert "INSERT INTO prompt_versions" in second_query


async def test_get_system_default_version_joins_prompts(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """get_system_default_version joint correctement prompts + prompt_versions."""
    from role_builder.db_helpers import prompts

    row_data = {"id": uuid4(), "template": "...", "prompt_name": "extractor"}
    stub_conn.fetchrow_return = row_data

    result = await prompts.get_system_default_version("extractor", pool=stub_pool)

    assert result == row_data
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "JOIN prompts" in query
    assert "is_system_default" in query
    assert "extractor" in args


async def test_list_versions_orders_by_version_number_desc(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """list_versions retourne triée ORDER BY version_number DESC."""
    from role_builder.db_helpers import prompts

    prompt_id = uuid4()
    rows = [{"id": uuid4(), "version_number": 2}, {"id": uuid4(), "version_number": 1}]
    stub_conn.fetch_return = rows

    result = await prompts.list_versions(prompt_id, pool=stub_pool)

    assert result == rows
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY version_number DESC" in query
    assert prompt_id in args


async def test_get_version_by_id_returns_none_or_dict(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_version_by_id retourne None quand absent, dict sinon."""
    from role_builder.db_helpers import prompts

    version_id = uuid4()

    # Cas None
    stub_conn.fetchrow_return = None
    result = await prompts.get_version_by_id(version_id, pool=stub_pool)
    assert result is None

    # Cas dict
    row_data = {"id": version_id, "template": "..."}
    stub_conn.fetchrow_return = row_data
    stub_conn.calls.clear()
    result = await prompts.get_version_by_id(version_id, pool=stub_pool)
    assert result == row_data
