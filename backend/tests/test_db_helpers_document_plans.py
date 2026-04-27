"""Tests TDD pour db_helpers/document_plans.py."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest

# ---------------------------------------------------------------------------
# Stubs asyncpg pool
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "DELETE 0"

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_insert_document_plan_sends_correct_args_and_returns_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """insert_document_plan envoie INSERT avec args dans bon ordre,
    sérialise planned_documents JSON, retourne UUID via fetchval."""
    from role_builder.db_helpers import document_plans

    run_id = uuid4()
    role_project_id = uuid4()
    tenant_id = uuid4()
    section = "Role"
    planned_docs = [{"name": "doc-1", "brief": "Un brief.", "supporting_signals": [str(uuid4())]}]
    expected_uuid = uuid4()

    conn = _StubConn()
    conn.fetchval_return = expected_uuid
    pool = _StubPool(conn)

    result = await document_plans.insert_document_plan(
        run_id=run_id,
        role_project_id=role_project_id,
        tenant_id=tenant_id,
        section=section,
        planned_documents=planned_docs,
        pool=pool,
    )

    assert isinstance(result, UUID)
    assert result == expected_uuid

    # Vérifier qu'un fetchval a été émis
    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "fetchval"
    assert "INSERT" in query.upper()
    assert "document_plans" in query.lower()

    # Les args doivent être dans l'ordre : run_id, role_project_id, tenant_id, section, planned_documents_json
    assert args[0] == run_id
    assert args[1] == role_project_id
    assert args[2] == tenant_id
    assert args[3] == section
    # Le 5e argument doit être un JSON sérialisé
    parsed = json.loads(args[4])
    assert parsed == planned_docs


async def test_list_plans_by_run_query_order_by_created_at_asc(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_plans_by_run query contient ORDER BY created_at ASC."""
    from role_builder.db_helpers import document_plans

    run_id = uuid4()
    conn = _StubConn()
    conn.fetch_return = []
    pool = _StubPool(conn)

    result = await document_plans.list_plans_by_run(run_id, pool=pool)

    assert result == []
    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY created_at ASC" in query
    assert args[0] == run_id


async def test_list_plans_by_project_without_section_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_plans_by_project sans filtre section ne contient pas AND section."""
    from role_builder.db_helpers import document_plans

    role_project_id = uuid4()
    conn = _StubConn()
    conn.fetch_return = []
    pool = _StubPool(conn)

    await document_plans.list_plans_by_project(role_project_id, pool=pool)

    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "fetch"
    assert "AND section" not in query
    assert "ORDER BY created_at DESC" in query
    assert args[0] == role_project_id


async def test_list_plans_by_project_with_section_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """list_plans_by_project avec section → query contient AND section."""
    from role_builder.db_helpers import document_plans

    role_project_id = uuid4()
    conn = _StubConn()
    conn.fetch_return = []
    pool = _StubPool(conn)

    await document_plans.list_plans_by_project(role_project_id, section="Role", pool=pool)

    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "fetch"
    assert "section" in query.lower()
    # Le filtre de section doit être dans les args
    assert "Role" in args


async def test_get_latest_plan_per_section_uses_distinct_on_and_returns_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_latest_plan_per_section query contient DISTINCT ON (section) ;
    transforme la liste de rows en dict {section: row}."""
    from role_builder.db_helpers import document_plans

    role_project_id = uuid4()
    run_id = uuid4()
    plan_id_role = uuid4()
    plan_id_missions = uuid4()

    row_role = {
        "id": plan_id_role,
        "run_id": run_id,
        "role_project_id": role_project_id,
        "tenant_id": uuid4(),
        "section": "Role",
        "planned_documents": "[]",
        "created_at": None,
    }
    row_missions = {
        "id": plan_id_missions,
        "run_id": run_id,
        "role_project_id": role_project_id,
        "tenant_id": uuid4(),
        "section": "Missions",
        "planned_documents": "[]",
        "created_at": None,
    }

    conn = _StubConn()
    conn.fetch_return = [row_role, row_missions]
    pool = _StubPool(conn)

    result = await document_plans.get_latest_plan_per_section(role_project_id, pool=pool)

    assert len(conn.calls) == 1
    method, query, _args = conn.calls[0]
    assert method == "fetch"
    assert "DISTINCT ON (section)" in query

    # Le résultat doit être un dict {section: row}
    assert isinstance(result, dict)
    assert "Role" in result
    assert "Missions" in result
    assert result["Role"]["id"] == plan_id_role
    assert result["Missions"]["id"] == plan_id_missions


async def test_delete_plans_by_run_parses_delete_n() -> None:
    """delete_plans_by_run parse 'DELETE N' et retourne le count."""
    from role_builder.db_helpers import document_plans

    run_id = uuid4()
    conn = _StubConn()
    conn.execute_return = "DELETE 3"
    pool = _StubPool(conn)

    result = await document_plans.delete_plans_by_run(run_id, pool=pool)

    assert result == 3
    assert len(conn.calls) == 1
    method, query, args = conn.calls[0]
    assert method == "execute"
    assert "DELETE" in query.upper()
    assert args[0] == run_id


async def test_get_by_id_returns_none_when_not_found() -> None:
    """get_by_id retourne None quand fetchrow retourne None."""
    from role_builder.db_helpers import document_plans

    plan_id = uuid4()
    conn = _StubConn()
    conn.fetchrow_return = None
    pool = _StubPool(conn)

    result = await document_plans.get_by_id(plan_id, pool=pool)

    assert result is None


async def test_get_by_id_returns_dict_when_found() -> None:
    """get_by_id retourne un dict quand la row existe."""
    from role_builder.db_helpers import document_plans

    plan_id = uuid4()
    row = {
        "id": plan_id,
        "run_id": uuid4(),
        "role_project_id": uuid4(),
        "tenant_id": uuid4(),
        "section": "Skills",
        "planned_documents": "[]",
        "created_at": None,
    }
    conn = _StubConn()
    conn.fetchrow_return = row
    pool = _StubPool(conn)

    result = await document_plans.get_by_id(plan_id, pool=pool)

    assert result is not None
    assert result["id"] == plan_id
    assert result["section"] == "Skills"
