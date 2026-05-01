"""Tests TDD pour rebuild corpus (Phase 2 sous-projet E)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


# ---------------------------------------------------------------------------
# Helpers DB
# ---------------------------------------------------------------------------


class _StubConn:
    def __init__(self, execute_tag: str = "DELETE 0") -> None:
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
async def test_delete_by_project_returns_rowcount() -> None:
    from role_builder.db_helpers.corpus_chunks import delete_by_project

    conn = _StubConn(execute_tag="DELETE 42")
    pool = _StubPool(conn)
    project_id = uuid4()

    rowcount = await delete_by_project(project_id, pool=pool)
    assert rowcount == 42
    assert "DELETE FROM corpus_chunks" in conn.calls[0][0]
    assert conn.calls[0][1] == (project_id,)


@pytest.mark.asyncio
async def test_enqueue_for_project_returns_rowcount() -> None:
    from role_builder.db_helpers.chunking_jobs import enqueue_for_project

    conn = _StubConn(execute_tag="INSERT 0 7")
    pool = _StubPool(conn)
    project_id = uuid4()

    rowcount = await enqueue_for_project(project_id, pool=pool)
    assert rowcount == 7
    sql = conn.calls[0][0]
    assert "INSERT INTO chunking_jobs" in sql
    assert "transcript_s3_key IS NOT NULL" in sql
    assert "FROM source_items" in sql
    assert conn.calls[0][1] == (project_id,)


@pytest.mark.asyncio
async def test_enqueue_for_project_zero_when_no_transcripts() -> None:
    from role_builder.db_helpers.chunking_jobs import enqueue_for_project

    conn = _StubConn(execute_tag="INSERT 0 0")
    pool = _StubPool(conn)
    rowcount = await enqueue_for_project(uuid4(), pool=pool)
    assert rowcount == 0


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


def test_rebuild_corpus_202_with_counts(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import corpus as route

    project_id = uuid4()

    async def fake_get(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return {"id": pid, "user_id": _FIXED_USER_ID, "tenant_id": uuid4()}

    async def fake_delete(pid: UUID, *, pool: Any) -> int:
        return 42

    async def fake_enqueue(pid: UUID, *, pool: Any) -> int:
        return 7

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get)
    monkeypatch.setattr(route.chunks_helper, "delete_by_project", fake_delete)
    monkeypatch.setattr(
        route.chunking_jobs_helper, "enqueue_for_project", fake_enqueue,
    )

    resp = client.post(f"/api/role-projects/{project_id}/corpus/rebuild")
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"deleted_chunks": 42, "enqueued_jobs": 7}


def test_rebuild_corpus_404_when_project_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import corpus as route

    async def fake_get(pid: UUID, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get)
    resp = client.post(f"/api/role-projects/{uuid4()}/corpus/rebuild")
    assert resp.status_code == 404


def test_rebuild_corpus_403_when_not_owner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import corpus as route

    other_user = uuid4()  # ≠ _FIXED_USER_ID

    async def fake_get(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return {"id": pid, "user_id": other_user, "tenant_id": uuid4()}

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get)
    resp = client.post(f"/api/role-projects/{uuid4()}/corpus/rebuild")
    assert resp.status_code == 403
