"""Tests routes Sprint 7 Phase D — lecture/édition role_documents.

Pattern : TestClient sync + monkeypatch des helpers db_helpers.role_documents.
Auth est désactivée par la fixture `client` (disable_auth=True).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def _make_doc_row(
    doc_id: UUID | None = None,
    project_id: UUID | None = None,
    section: str = "Role",
    name: str = "principe-empathie",
    version: int = 1,
    is_current: bool = True,
    locked: bool = False,
    content: str = "# Contenu",
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "id": doc_id or uuid4(),
        "role_project_id": project_id or uuid4(),
        "tenant_id": uuid4(),
        "section": section,
        "name": name,
        "content": content,
        "source_run_id": uuid4(),
        "version": version,
        "is_current": is_current,
        "locked": locked,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# GET /role-projects/{id}/role-documents
# ---------------------------------------------------------------------------


def test_list_grouped_returns_sections_dict_without_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET liste les docs groupés par section, sans le champ ``content``."""
    from role_builder.routes import role_documents as route

    project_id = uuid4()
    doc1 = _make_doc_row(project_id=project_id, section="Role", name="a")
    doc2 = _make_doc_row(project_id=project_id, section="Role", name="b")
    doc3 = _make_doc_row(project_id=project_id, section="Missions", name="m1")

    async def fake_grouped(pid: UUID, *, pool: Any) -> dict[str, list[dict[str, Any]]]:
        assert pid == project_id
        return {"Role": [doc1, doc2], "Missions": [doc3]}

    monkeypatch.setattr(
        route.role_documents,
        "list_current_by_project_grouped",
        fake_grouped,
    )

    resp = client.get(f"/api/role-projects/{project_id}/role-documents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "sections" in body
    assert set(body["sections"].keys()) == {"Role", "Missions"}
    assert len(body["sections"]["Role"]) == 2
    # Summary : pas de ``content``
    assert all("content" not in d for d in body["sections"]["Role"])
    assert all("name" in d and "version" in d and "locked" in d
               for d in body["sections"]["Role"])


# ---------------------------------------------------------------------------
# GET /role-documents/{id}
# ---------------------------------------------------------------------------


def test_get_document_returns_full_content(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    doc = _make_doc_row()

    async def fake_get(doc_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        assert doc_id == doc["id"]
        return doc

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)

    resp = client.get(f"/api/role-documents/{doc['id']}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(doc["id"])
    assert body["content"] == "# Contenu"


def test_get_document_404_when_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    async def fake_get(doc_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)

    resp = client.get(f"/api/role-documents/{uuid4()}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /role-documents/{id}/versions
# ---------------------------------------------------------------------------


def test_list_versions_returns_versions_desc(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    project_id = uuid4()
    doc_id = uuid4()
    base = _make_doc_row(doc_id=doc_id, project_id=project_id)
    versions = [
        _make_doc_row(project_id=project_id, version=3, is_current=True),
        _make_doc_row(project_id=project_id, version=2, is_current=False),
        _make_doc_row(project_id=project_id, version=1, is_current=False),
    ]

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return base if d_id == doc_id else None

    async def fake_list_versions(
        pid: UUID, section: str, name: str, *, pool: Any
    ) -> list[dict[str, Any]]:
        assert pid == project_id
        assert section == base["section"]
        assert name == base["name"]
        return versions

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)
    monkeypatch.setattr(route.role_documents, "list_versions", fake_list_versions)

    resp = client.get(f"/api/role-documents/{doc_id}/versions")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 3
    assert body[0]["version"] > body[-1]["version"]


def test_list_versions_404_when_doc_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)

    resp = client.get(f"/api/role-documents/{uuid4()}/versions")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /role-documents/{id}
# ---------------------------------------------------------------------------


def test_patch_updates_content_and_returns_full_doc(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    doc_id = uuid4()
    updated_doc = _make_doc_row(doc_id=doc_id, content="édité à la main")
    update_calls: list[tuple[UUID, str]] = []

    async def fake_update(d_id: UUID, content: str, *, pool: Any) -> None:
        update_calls.append((d_id, content))

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return updated_doc

    monkeypatch.setattr(route.role_documents, "update_content", fake_update)
    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)

    resp = client.patch(
        f"/api/role-documents/{doc_id}",
        json={"content": "édité à la main"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["content"] == "édité à la main"
    assert update_calls == [(doc_id, "édité à la main")]


def test_patch_404_when_update_raises_value_error(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    async def fake_update(d_id: UUID, content: str, *, pool: Any) -> None:
        raise ValueError(f"doc_id {d_id} not found")

    monkeypatch.setattr(route.role_documents, "update_content", fake_update)

    resp = client.patch(
        f"/api/role-documents/{uuid4()}",
        json={"content": "x"},
    )
    assert resp.status_code == 404


def test_patch_422_when_content_empty(client: TestClient) -> None:
    """Pydantic min_length=1 → 422 sans toucher au helper."""
    resp = client.patch(
        f"/api/role-documents/{uuid4()}",
        json={"content": ""},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /role-documents/{id}/lock + /unlock
# ---------------------------------------------------------------------------


def test_lock_calls_helper_and_returns_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    doc = _make_doc_row()
    lock_calls: list[UUID] = []

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return doc

    async def fake_lock(d_id: UUID, *, pool: Any) -> None:
        lock_calls.append(d_id)

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)
    monkeypatch.setattr(route.role_documents, "lock_document", fake_lock)

    resp = client.post(f"/api/role-documents/{doc['id']}/lock")
    assert resp.status_code == 200
    assert resp.json() == {"status": "locked"}
    assert lock_calls == [doc["id"]]


def test_unlock_calls_helper_and_returns_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    doc = _make_doc_row()
    unlock_calls: list[UUID] = []

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return doc

    async def fake_unlock(d_id: UUID, *, pool: Any) -> None:
        unlock_calls.append(d_id)

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)
    monkeypatch.setattr(route.role_documents, "unlock_document", fake_unlock)

    resp = client.post(f"/api/role-documents/{doc['id']}/unlock")
    assert resp.status_code == 200
    assert resp.json() == {"status": "unlocked"}
    assert unlock_calls == [doc["id"]]


def test_lock_404_when_doc_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_documents as route

    async def fake_get(d_id: UUID, *, pool: Any) -> dict[str, Any] | None:
        return None

    monkeypatch.setattr(route.role_documents, "get_by_id", fake_get)

    resp = client.post(f"/api/role-documents/{uuid4()}/lock")
    assert resp.status_code == 404
