"""Tests for db_helpers.role_projects — get_user_id_for_project + get_by_id + update_identity."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.execute_return: str = "UPDATE 1"

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

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


async def test_get_by_id_returns_none_when_not_found(stub_conn: _StubConn, stub_pool: Any) -> None:
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


async def test_get_by_id_returns_dict_when_found(stub_conn: _StubConn, stub_pool: Any) -> None:
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


async def test_update_identity_sends_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_identity envoie UPDATE role_projects SET identity avec les bons args."""
    from role_builder.db_helpers import role_projects

    stub_conn.execute_return = "UPDATE 1"
    project_id = uuid4()
    identity_text = "Je suis un agent spécialisé en analyse financière."

    await role_projects.update_identity(project_id, identity_text, pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE role_projects" in query
    assert "identity" in query.lower()
    assert args[0] == project_id
    assert args[1] == identity_text


async def test_update_identity_raises_value_error_when_not_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_identity lève ValueError si aucune ligne touchée (UPDATE 0)."""
    from role_builder.db_helpers import role_projects

    stub_conn.execute_return = "UPDATE 0"
    project_id = uuid4()

    with pytest.raises(ValueError, match=str(project_id)):
        await role_projects.update_identity(project_id, "some identity", pool=stub_pool)


async def test_update_mistral_secret_ref_sends_update(stub_conn: _StubConn, stub_pool: Any) -> None:
    """update_mistral_secret_ref envoie UPDATE role_projects SET mistral_secret_ref."""
    from role_builder.db_helpers import role_projects

    stub_conn.execute_return = "UPDATE 1"
    project_id = uuid4()
    secret_ref = "mistral-prod-key"

    await role_projects.update_mistral_secret_ref(project_id, secret_ref, pool=stub_pool)

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE role_projects" in query
    assert "mistral_secret_ref" in query
    assert args[0] == project_id
    assert args[1] == secret_ref


async def test_update_mistral_secret_ref_raises_value_error_when_not_found(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_mistral_secret_ref lève ValueError si execute retourne 'UPDATE 0'."""
    from role_builder.db_helpers import role_projects

    stub_conn.execute_return = "UPDATE 0"
    project_id = uuid4()

    with pytest.raises(ValueError, match=str(project_id)):
        await role_projects.update_mistral_secret_ref(project_id, None, pool=stub_pool)
