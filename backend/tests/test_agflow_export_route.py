"""Tests pour routes.agflow_export — preview-zip, push-to-agflow, generate-prompts, download-zip."""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers de fabrication de données fictives
# ---------------------------------------------------------------------------


def _make_project(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": uuid4(),
        "display_name": "UX Designer Clea",
        "description": "Agent expert en design UX",
        "identity": "## Identity markdown",
        "target_role_id": None,
        "language": "fr",
    }
    base.update(overrides)
    return base


def _make_doc(name: str, section: str = "Role", content: str = "x" * 100) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "section": section,
        "name": name,
        "content": content,
        "is_current": True,
        "version": 1,
    }


def _make_docs_by_section() -> dict[str, list[dict[str, Any]]]:
    return {
        "Role": [_make_doc("Identité", section="Role")],
        "Missions": [_make_doc("Missions principales", section="Missions")],
        "Skills": [_make_doc("Compétences clés", section="Skills")],
    }


def _make_httpx_error(status_code: int = 500) -> httpx.HTTPStatusError:
    fake_response = Mock(spec=httpx.Response)
    fake_response.status_code = status_code
    fake_request = httpx.Request("POST", "http://test")
    return httpx.HTTPStatusError(
        f"upstream {status_code}", request=fake_request, response=fake_response
    )


# ---------------------------------------------------------------------------
# T1 — GET /preview-zip OK → 200 + sections + ready_to_push=True
# ---------------------------------------------------------------------------


def test_preview_zip_ok_returns_200_with_sections(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /preview-zip → 200, sections présentes, ready_to_push=True."""
    from role_builder.routes import agflow_export as route

    project = _make_project(identity="## Identity markdown")
    docs_by_section = _make_docs_by_section()

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_grouped(pid: UUID, *, pool: Any) -> dict[str, list[dict[str, Any]]]:
        return docs_by_section

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route.role_documents, "list_current_by_project_grouped", fake_grouped)

    resp = client.get(f"/api/role-projects/{project['id']}/preview-zip")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["display_name"] == "UX Designer Clea"
    assert body["ready_to_push"] is True
    assert body["missing"] == []
    assert len(body["sections"]) == 3
    section_names = {s["name"] for s in body["sections"]}
    assert section_names == {"Role", "Missions", "Skills"}


# ---------------------------------------------------------------------------
# T2 — GET /preview-zip project inexistant → 404
# ---------------------------------------------------------------------------


def test_preview_zip_project_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /preview-zip → 404 si project inconnu."""
    from role_builder.routes import agflow_export as route

    async def fake_get_project(pid: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)

    resp = client.get(f"/api/role-projects/{uuid4()}/preview-zip")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "role project not found"


# ---------------------------------------------------------------------------
# T3 — GET /preview-zip missing identity → ready_to_push=False
# ---------------------------------------------------------------------------


def test_preview_zip_missing_identity_returns_not_ready(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /preview-zip → ready_to_push=False quand identity vide."""
    from role_builder.routes import agflow_export as route

    project = _make_project(identity=None)
    docs_by_section = _make_docs_by_section()

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_grouped(pid: UUID, *, pool: Any) -> dict[str, list[dict[str, Any]]]:
        return docs_by_section

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route.role_documents, "list_current_by_project_grouped", fake_grouped)

    resp = client.get(f"/api/role-projects/{project['id']}/preview-zip")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ready_to_push"] is False
    assert "Identity not generated" in body["missing"]


# ---------------------------------------------------------------------------
# T4 — POST /push-to-agflow OK → 200 + PushToAgflowResponse
# ---------------------------------------------------------------------------


def test_push_to_agflow_ok_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /push-to-agflow → 200 + corps PushToAgflowResponse."""
    from role_builder.routes import agflow_export as route

    project_id = uuid4()
    agflow_role_id = str(uuid4())

    async def fake_push(pid: UUID, *, generate_prompts: bool, pool: Any) -> dict[str, Any]:
        assert pid == project_id
        return {
            "agflow_role_id": agflow_role_id,
            "zip_size_bytes": 1024,
            "documents_count": 3,
            "prompt_generated": generate_prompts,
            "agflow_url": f"https://ag.flow/admin/roles/{agflow_role_id}",
        }

    monkeypatch.setattr(route.agflow_push, "push_role_to_agflow", fake_push)

    resp = client.post(
        f"/api/role-projects/{project_id}/push-to-agflow",
        json={"generate_prompts": False},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agflow_role_id"] == agflow_role_id
    assert body["zip_size_bytes"] == 1024
    assert body["documents_count"] == 3
    assert body["prompt_generated"] is False


# ---------------------------------------------------------------------------
# T5 — POST /push-to-agflow RuntimeError "not found" → 404
# ---------------------------------------------------------------------------


def test_push_to_agflow_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /push-to-agflow → 404 si RuntimeError 'not found'."""
    from role_builder.routes import agflow_export as route

    async def fake_push(pid: UUID, *, generate_prompts: bool, pool: Any) -> None:
        raise RuntimeError(f"role_project {pid} not found")

    monkeypatch.setattr(route.agflow_push, "push_role_to_agflow", fake_push)

    resp = client.post(
        f"/api/role-projects/{uuid4()}/push-to-agflow",
        json={},
    )
    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# T6 — POST /push-to-agflow RuntimeError "missing pieces" → 400
# ---------------------------------------------------------------------------


def test_push_to_agflow_missing_pieces_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /push-to-agflow → 400 si RuntimeError 'missing pieces'."""
    from role_builder.routes import agflow_export as route

    async def fake_push(pid: UUID, *, generate_prompts: bool, pool: Any) -> None:
        raise RuntimeError("cannot push: missing pieces — ['Identity not generated']")

    monkeypatch.setattr(route.agflow_push, "push_role_to_agflow", fake_push)

    resp = client.post(
        f"/api/role-projects/{uuid4()}/push-to-agflow",
        json={},
    )
    assert resp.status_code == 400, resp.text
    assert "missing pieces" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# T7 — POST /push-to-agflow httpx.HTTPStatusError → 502
# ---------------------------------------------------------------------------


def test_push_to_agflow_upstream_error_returns_502(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /push-to-agflow → 502 si ag.flow retourne une erreur HTTP."""
    from role_builder.routes import agflow_export as route

    exc = _make_httpx_error(500)

    async def fake_push(pid: UUID, *, generate_prompts: bool, pool: Any) -> None:
        raise exc

    monkeypatch.setattr(route.agflow_push, "push_role_to_agflow", fake_push)

    resp = client.post(
        f"/api/role-projects/{uuid4()}/push-to-agflow",
        json={},
    )
    assert resp.status_code == 502, resp.text
    assert "ag.flow returned HTTP 500" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# T8 — POST /generate-prompts-on-agflow sans target_role_id → 400
# ---------------------------------------------------------------------------


def test_generate_prompts_without_target_role_id_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /generate-prompts-on-agflow → 400 si pas de target_role_id."""
    from role_builder.routes import agflow_export as route

    project = _make_project(target_role_id=None)

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)

    resp = client.post(f"/api/role-projects/{project['id']}/generate-prompts-on-agflow")
    assert resp.status_code == 400, resp.text
    assert "no target_role_id" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# T9 — POST /generate-prompts-on-agflow OK → 200
# ---------------------------------------------------------------------------


def test_generate_prompts_ok_returns_200(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /generate-prompts-on-agflow → 200 + GeneratePromptsResponse."""
    from role_builder.routes import agflow_export as route

    agflow_role_id = str(uuid4())
    project = _make_project(target_role_id=agflow_role_id)

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    class _FakeClient:
        async def generate_prompts(self, role_id: str) -> dict[str, Any]:
            return {"ok": True}

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route, "get_agflow_admin_client", lambda: _FakeClient())

    resp = client.post(f"/api/role-projects/{project['id']}/generate-prompts-on-agflow")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "generated"
    assert body["target_role_id"] == agflow_role_id


# ---------------------------------------------------------------------------
# T10 — POST /generate-prompts-on-agflow project inconnu → 404
# ---------------------------------------------------------------------------


def test_generate_prompts_project_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /generate-prompts-on-agflow → 404 si project inconnu."""
    from role_builder.routes import agflow_export as route

    async def fake_get_project(pid: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)

    resp = client.post(f"/api/role-projects/{uuid4()}/generate-prompts-on-agflow")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "role project not found"


# ---------------------------------------------------------------------------
# T11 — GET /download-zip OK → 200, content-type application/zip
# ---------------------------------------------------------------------------


def test_download_zip_ok_returns_zip_bytes(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /download-zip → 200, content-type application/zip, Content-Disposition."""
    from role_builder.routes import agflow_export as route
    from role_builder.services.agflow.exporter import BuildResult

    project = _make_project()
    docs_by_section = _make_docs_by_section()
    fake_zip = b"PK\x03\x04fake-zip-content"

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_grouped(pid: UUID, *, pool: Any) -> dict[str, list[dict[str, Any]]]:
        return docs_by_section

    def fake_build_role_zip(
        proj: dict[str, Any], docs: dict[str, list[dict[str, Any]]]
    ) -> BuildResult:
        return BuildResult(zip_bytes=fake_zip, role_json={}, documents_count=3)

    # patch check_missing_pieces pour retourner [] (rien de manquant)
    monkeypatch.setattr(route.agflow_push, "check_missing_pieces", lambda p, d: [])
    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route.role_documents, "list_current_by_project_grouped", fake_grouped)
    monkeypatch.setattr(route, "build_role_zip", fake_build_role_zip)

    resp = client.get(f"/api/role-projects/{project['id']}/download-zip")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/zip"
    assert "attachment" in resp.headers["content-disposition"]
    assert resp.content == fake_zip


# ---------------------------------------------------------------------------
# T12 — GET /download-zip missing pieces → 400
# ---------------------------------------------------------------------------


def test_download_zip_missing_pieces_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /download-zip → 400 si pièces manquantes."""
    from role_builder.routes import agflow_export as route

    project = _make_project(identity=None)
    docs_by_section: dict[str, list[dict[str, Any]]] = {}

    async def fake_get_project(pid: UUID, *, pool: Any) -> dict[str, Any]:
        return project

    async def fake_grouped(pid: UUID, *, pool: Any) -> dict[str, list[dict[str, Any]]]:
        return docs_by_section

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_project)
    monkeypatch.setattr(route.role_documents, "list_current_by_project_grouped", fake_grouped)

    resp = client.get(f"/api/role-projects/{project['id']}/download-zip")
    assert resp.status_code == 400, resp.text
    assert "missing pieces" in resp.json()["detail"]
