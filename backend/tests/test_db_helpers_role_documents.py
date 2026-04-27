"""Tests TDD pour db_helpers/role_documents.py — CRUD role_documents versionné."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

# ---------------------------------------------------------------------------
# Stubs asyncpg pool (pattern db_helpers_prompts)
# ---------------------------------------------------------------------------


class _StubTransactionCtx:
    """Context manager no-op qui simule conn.transaction()."""

    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        self._conn.transaction_count += 1
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.execute_return: str = "UPDATE 1"
        self.transaction_count: int = 0

    def transaction(self) -> _StubTransactionCtx:
        return _StubTransactionCtx(self)

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


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


# ---------------------------------------------------------------------------
# Tests E1.1 — insert_role_document(is_current=False) : INSERT simple
# ---------------------------------------------------------------------------


async def test_insert_role_document_not_current_simple_insert(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_role_document(is_current=False) : 2 appels (fetchval version + fetchval insert),
    pas de transaction."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    tenant_id = uuid4()
    run_id = uuid4()
    doc_id = uuid4()

    # Premier fetchval = version (COALESCE MAX), second = doc id
    call_idx = 0

    async def _fetchval(query: str, *args: Any) -> Any:
        nonlocal call_idx
        stub_conn.calls.append(("fetchval", query, args))
        if call_idx == 0:
            call_idx += 1
            return 2  # version max+1
        return doc_id

    stub_conn.fetchval = _fetchval  # type: ignore[method-assign]

    result = await role_documents.insert_role_document(
        role_project_id=project_id,
        tenant_id=tenant_id,
        section="Role",
        name="principle",
        content="# Content",
        source_run_id=run_id,
        is_current=False,
        pool=stub_pool,
    )

    assert result == doc_id
    # Pas de transaction
    assert stub_conn.transaction_count == 0
    # 2 fetchval : calcul version + INSERT
    fetchval_calls = [c for c in stub_conn.calls if c[0] == "fetchval"]
    assert len(fetchval_calls) == 2
    # Vérifier requête version
    version_query = fetchval_calls[0][1]
    assert "COALESCE" in version_query
    assert "MAX(version)" in version_query
    # Vérifier requête insert
    insert_query = fetchval_calls[1][1]
    assert "INSERT INTO role_documents" in insert_query
    assert "RETURNING id" in insert_query


# ---------------------------------------------------------------------------
# Tests E1.2 — insert_role_document(is_current=True) : transaction
# ---------------------------------------------------------------------------


async def test_insert_role_document_current_uses_transaction(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_role_document(is_current=True) : transaction ouverte,
    UPDATE ancien current + INSERT nouveau."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    tenant_id = uuid4()
    run_id = uuid4()
    doc_id = uuid4()

    call_idx = 0

    async def _fetchval(query: str, *args: Any) -> Any:
        nonlocal call_idx
        stub_conn.calls.append(("fetchval", query, args))
        if call_idx == 0:
            call_idx += 1
            return 1  # version
        return doc_id

    stub_conn.fetchval = _fetchval  # type: ignore[method-assign]

    result = await role_documents.insert_role_document(
        role_project_id=project_id,
        tenant_id=tenant_id,
        section="Role",
        name="principle",
        content="# Content",
        source_run_id=run_id,
        is_current=True,
        pool=stub_pool,
    )

    assert result == doc_id
    # Transaction ouverte
    assert stub_conn.transaction_count == 1
    # UPDATE sur ancien current
    execute_calls = [c for c in stub_conn.calls if c[0] == "execute"]
    assert len(execute_calls) == 1
    update_query = execute_calls[0][1]
    assert "UPDATE role_documents" in update_query
    assert "is_current = false" in update_query


# ---------------------------------------------------------------------------
# Tests E1.3 — get_by_id : None / dict
# ---------------------------------------------------------------------------


async def test_get_by_id_returns_none_when_absent(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_by_id retourne None si fetchrow retourne None."""
    from role_builder.db_helpers import role_documents

    stub_conn.fetchrow_return = None
    result = await role_documents.get_by_id(uuid4(), pool=stub_pool)
    assert result is None
    assert len(stub_conn.calls) == 1
    method, query, _ = stub_conn.calls[0]
    assert method == "fetchrow"
    assert "FROM role_documents" in query


async def test_get_by_id_returns_dict_when_found(stub_conn: _StubConn, stub_pool: Any) -> None:
    """get_by_id retourne dict si fetchrow retourne une row."""
    from role_builder.db_helpers import role_documents

    doc_id = uuid4()
    stub_conn.fetchrow_return = {"id": doc_id, "name": "principle", "content": "..."}
    result = await role_documents.get_by_id(doc_id, pool=stub_pool)
    assert result is not None
    assert result["id"] == doc_id


# ---------------------------------------------------------------------------
# Tests E1.4-5 — list_by_section
# ---------------------------------------------------------------------------


async def test_list_by_section_not_filtered(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_by_section(only_current=False) : query sans AND is_current, ORDER BY name ASC, version DESC."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    stub_conn.fetch_return = []
    result = await role_documents.list_by_section(project_id, "Role", pool=stub_pool)
    assert result == []
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY name ASC, version DESC" in query
    assert "AND is_current = true" not in query
    assert project_id in args
    assert "Role" in args


async def test_list_by_section_only_current(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_by_section(only_current=True) : query AVEC AND is_current = true."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    stub_conn.fetch_return = []
    await role_documents.list_by_section(project_id, "Missions", only_current=True, pool=stub_pool)
    assert len(stub_conn.calls) == 1
    _, query, _ = stub_conn.calls[0]
    assert "AND is_current = true" in query


# ---------------------------------------------------------------------------
# Tests E1.6 — list_current_by_project
# ---------------------------------------------------------------------------


async def test_list_current_by_project_query(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_current_by_project : query contient WHERE role_project_id = $1 AND is_current = true."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    stub_conn.fetch_return = []
    result = await role_documents.list_current_by_project(project_id, pool=stub_pool)
    assert result == []
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "WHERE role_project_id = $1" in query
    assert "AND is_current = true" in query
    assert project_id in args


# ---------------------------------------------------------------------------
# Tests E1.7 — list_versions
# ---------------------------------------------------------------------------


async def test_list_versions_query(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_versions : query contient WHERE role_project_id=$1 AND section=$2 AND name=$3
    ORDER BY version DESC."""
    from role_builder.db_helpers import role_documents

    project_id = uuid4()
    stub_conn.fetch_return = []
    await role_documents.list_versions(project_id, "Role", "principle", pool=stub_pool)
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "ORDER BY version DESC" in query
    assert project_id in args
    assert "Role" in args
    assert "principle" in args


# ---------------------------------------------------------------------------
# Tests E1.8-9 — set_current
# ---------------------------------------------------------------------------


async def test_set_current_unknown_id_raises_value_error(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """set_current(unknown_id) : fetchrow→None, lève ValueError, pas d'UPDATE."""
    from role_builder.db_helpers import role_documents

    stub_conn.fetchrow_return = None
    with pytest.raises(ValueError, match="doc_id"):
        await role_documents.set_current(uuid4(), pool=stub_pool)

    execute_calls = [c for c in stub_conn.calls if c[0] == "execute"]
    assert len(execute_calls) == 0


async def test_set_current_known_id_transaction(stub_conn: _StubConn, stub_pool: Any) -> None:
    """set_current(known_id) : transaction (UPDATE old + UPDATE new)."""
    from role_builder.db_helpers import role_documents

    doc_id = uuid4()
    project_id = uuid4()
    stub_conn.fetchrow_return = {
        "role_project_id": project_id,
        "section": "Role",
        "name": "principle",
    }

    await role_documents.set_current(doc_id, pool=stub_pool)

    assert stub_conn.transaction_count == 1
    execute_calls = [c for c in stub_conn.calls if c[0] == "execute"]
    # 2 UPDATE : désactiver ancien + activer nouveau
    assert len(execute_calls) == 2
    # Premier UPDATE : is_current = false
    assert "is_current = false" in execute_calls[0][1]
    # Deuxième UPDATE : is_current = true
    assert "is_current = true" in execute_calls[1][1]


# ---------------------------------------------------------------------------
# Tests E1.10 — lock_document / unlock_document
# ---------------------------------------------------------------------------


async def test_lock_document_updates_locked_true(stub_conn: _StubConn, stub_pool: Any) -> None:
    """lock_document : UPDATE locked = true."""
    from role_builder.db_helpers import role_documents

    doc_id = uuid4()
    await role_documents.lock_document(doc_id, pool=stub_pool)
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "locked = true" in query
    assert doc_id in args


async def test_unlock_document_updates_locked_false(stub_conn: _StubConn, stub_pool: Any) -> None:
    """unlock_document : UPDATE locked = false."""
    from role_builder.db_helpers import role_documents

    doc_id = uuid4()
    await role_documents.unlock_document(doc_id, pool=stub_pool)
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "locked = false" in query
    assert doc_id in args


# ---------------------------------------------------------------------------
# Tests E1.11 — delete_documents_by_run
# ---------------------------------------------------------------------------


async def test_delete_documents_by_run_returns_count(stub_conn: _StubConn, stub_pool: Any) -> None:
    """delete_documents_by_run : DELETE + retourne count."""
    from role_builder.db_helpers import role_documents

    run_id = uuid4()
    stub_conn.execute_return = "DELETE 3"
    count = await role_documents.delete_documents_by_run(run_id, pool=stub_pool)
    assert count == 3
    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "DELETE FROM role_documents" in query
    assert "source_run_id" in query
    assert run_id in args
