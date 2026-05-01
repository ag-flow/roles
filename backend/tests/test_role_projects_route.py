"""Tests pour routes.role_projects — GET /api/role-projects."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_FIXED_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_project_row(
    project_id: UUID | None = None,
    display_name: str = "Mon projet",
    mistral_secret_ref: str | None = None,
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de role_projects."""
    now = datetime.now(tz=UTC)
    return {
        "id": project_id or uuid4(),
        "tenant_id": _FIXED_TENANT_ID,
        "user_id": _FIXED_USER_ID,
        "display_name": display_name,
        "description": None,
        "global_directives": None,
        "mistral_secret_ref": mistral_secret_ref,
        "identity": None,
        "target_role_id": None,
        "language": None,
        "is_public": False,
        "keep_audio": True,
        "created_at": now,
        "updated_at": now,
    }


# ---------------------------------------------------------------------------
# T1 — GET /role-projects liste vide → 200 + []
# ---------------------------------------------------------------------------


def test_list_role_projects_empty_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects → 200 + [] si aucun projet."""
    from role_builder.routes import role_projects as route

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict]:
        return []

    monkeypatch.setattr(route.role_projects_helper, "list_for_user", fake_list)

    resp = client.get("/api/role-projects")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


# ---------------------------------------------------------------------------
# T2 — GET /role-projects avec 2 projets → 200 + liste sérialisée
# ---------------------------------------------------------------------------


def test_list_role_projects_returns_two_projects(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects → 200 + list[RoleProjectOut] avec 2 entrées."""
    from role_builder.routes import role_projects as route

    id1 = uuid4()
    id2 = uuid4()
    rows = [
        _make_project_row(project_id=id1, display_name="Projet Alpha", mistral_secret_ref="my-ref"),
        _make_project_row(project_id=id2, display_name="Projet Beta"),
    ]

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict]:
        return rows

    monkeypatch.setattr(route.role_projects_helper, "list_for_user", fake_list)

    resp = client.get("/api/role-projects")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["id"] == str(id1)
    assert body[0]["display_name"] == "Projet Alpha"
    assert body[0]["mistral_secret_ref"] == "my-ref"
    assert body[1]["id"] == str(id2)
    assert body[1]["display_name"] == "Projet Beta"
    assert body[1]["mistral_secret_ref"] is None


# ---------------------------------------------------------------------------
# Phase 2 sous-projet C — PATCH /role-projects/{id}/global-directives
# ---------------------------------------------------------------------------


def test_patch_global_directives_404_when_project_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_projects as route

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get_by_id)

    resp = client.patch(
        f"/api/role-projects/{uuid4()}/global-directives",
        json={"global_directives": "nouvelle directive"},
    )
    assert resp.status_code == 404


def test_patch_global_directives_403_when_not_owner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_projects as route

    other_user = uuid4()  # ≠ _FIXED_USER_ID
    project = _make_project_row()
    project["user_id"] = other_user

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get_by_id)

    resp = client.patch(
        f"/api/role-projects/{project['id']}/global-directives",
        json={"global_directives": "x"},
    )
    assert resp.status_code == 403


def test_patch_global_directives_204_and_marks_runs_obsolete(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import role_projects as route

    project = _make_project_row()
    update_calls: list[tuple[UUID, str | None]] = []
    obsolete_calls: list[UUID] = []

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_update(project_id: UUID, directives: str | None, *, pool: Any) -> None:
        update_calls.append((project_id, directives))

    async def fake_mark_obsolete(project_id: UUID, *, pool: Any) -> int:
        obsolete_calls.append(project_id)
        return 5

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        route.role_projects_helper, "update_global_directives", fake_update,
    )
    monkeypatch.setattr(route.runs_helper, "mark_obsolete_for_project", fake_mark_obsolete)

    resp = client.patch(
        f"/api/role-projects/{project['id']}/global-directives",
        json={"global_directives": "Sois concis et factuel."},
    )
    assert resp.status_code == 204, resp.text
    assert update_calls == [(project["id"], "Sois concis et factuel.")]
    assert obsolete_calls == [project["id"]]


def test_patch_global_directives_accepts_null(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """null reset les directives. is_obsolete est toujours déclenchée."""
    from role_builder.routes import role_projects as route

    project = _make_project_row()
    update_calls: list[tuple[UUID, str | None]] = []

    async def fake_get_by_id(project_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_update(project_id: UUID, directives: str | None, *, pool: Any) -> None:
        update_calls.append((project_id, directives))

    async def fake_mark_obsolete(project_id: UUID, *, pool: Any) -> int:
        return 0

    monkeypatch.setattr(route.role_projects_helper, "get_by_id", fake_get_by_id)
    monkeypatch.setattr(
        route.role_projects_helper, "update_global_directives", fake_update,
    )
    monkeypatch.setattr(route.runs_helper, "mark_obsolete_for_project", fake_mark_obsolete)

    resp = client.patch(
        f"/api/role-projects/{project['id']}/global-directives",
        json={"global_directives": None},
    )
    assert resp.status_code == 204, resp.text
    assert update_calls == [(project["id"], None)]
