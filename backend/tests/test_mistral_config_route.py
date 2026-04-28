"""Tests pour routes.mistral_config — GET/PUT mistral-config par role_project."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project_row(
    project_id: UUID | None = None,
    mistral_secret_ref: str | None = "mistral-prod-key",
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de la table role_projects."""
    return {
        "id": project_id or uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "name": "Mon projet",
        "mistral_secret_ref": mistral_secret_ref,
    }


# ---------------------------------------------------------------------------
# T1 — GET projet avec secret_ref configuré → 200, status="configured"
# ---------------------------------------------------------------------------


def test_get_mistral_config_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects/{id}/mistral-config → 200, status=configured."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()
    project_row = _make_project_row(project_id=project_id, mistral_secret_ref="mistral-prod-key")

    async def fake_get_by_id(rp_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project_row

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_by_id)

    resp = client.get(f"/api/role-projects/{project_id}/mistral-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret_ref"] == "mistral-prod-key"
    assert body["status"] == "configured"


# ---------------------------------------------------------------------------
# T2 — GET projet avec secret_ref=None → 200, status="not-configured"
# ---------------------------------------------------------------------------


def test_get_mistral_config_none_secret_ref(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects/{id}/mistral-config → 200, status=not-configured si secret_ref=None."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()
    project_row = _make_project_row(project_id=project_id, mistral_secret_ref=None)

    async def fake_get_by_id(rp_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project_row

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_by_id)

    resp = client.get(f"/api/role-projects/{project_id}/mistral-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret_ref"] is None
    assert body["status"] == "not-configured"


# ---------------------------------------------------------------------------
# T3 — GET projet avec secret_ref="" (string vide) → 200, status="not-configured"
# ---------------------------------------------------------------------------


def test_get_mistral_config_empty_secret_ref(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects/{id}/mistral-config → 200, status=not-configured si secret_ref=""."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()
    project_row = _make_project_row(project_id=project_id, mistral_secret_ref="")

    async def fake_get_by_id(rp_id: UUID, *, pool: Any) -> dict[str, Any]:
        return project_row

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_by_id)

    resp = client.get(f"/api/role-projects/{project_id}/mistral-config")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret_ref"] == ""
    assert body["status"] == "not-configured"


# ---------------------------------------------------------------------------
# T4 — GET projet inexistant → 404
# ---------------------------------------------------------------------------


def test_get_mistral_config_project_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/role-projects/{id}/mistral-config → 404 si projet inexistant."""
    from role_builder.routes import mistral_config as route

    async def fake_get_by_id(rp_id: UUID, *, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.role_projects, "get_by_id", fake_get_by_id)

    resp = client.get(f"/api/role-projects/{uuid4()}/mistral-config")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "role project not found"


# ---------------------------------------------------------------------------
# T5 — PUT body {"secret_ref": "mistral-prod-key"} → 200, status="configured"
# ---------------------------------------------------------------------------


def test_put_mistral_config_sets_secret_ref(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /api/role-projects/{id}/mistral-config → 200, status=configured + update appelé."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_update(rp_id: UUID, secret_ref: str | None, *, pool: Any) -> None:
        captured["project_id"] = rp_id
        captured["secret_ref"] = secret_ref

    monkeypatch.setattr(route.role_projects, "update_mistral_secret_ref", fake_update)

    resp = client.put(
        f"/api/role-projects/{project_id}/mistral-config",
        json={"secret_ref": "mistral-prod-key"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret_ref"] == "mistral-prod-key"
    assert body["status"] == "configured"
    assert captured["project_id"] == project_id
    assert captured["secret_ref"] == "mistral-prod-key"


# ---------------------------------------------------------------------------
# T6 — PUT body {"secret_ref": null} → 200, status="not-configured" + update appelé avec None
# ---------------------------------------------------------------------------


def test_put_mistral_config_clears_secret_ref(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /api/role-projects/{id}/mistral-config → 200, status=not-configured si secret_ref=null."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_update(rp_id: UUID, secret_ref: str | None, *, pool: Any) -> None:
        captured["secret_ref"] = secret_ref

    monkeypatch.setattr(route.role_projects, "update_mistral_secret_ref", fake_update)

    resp = client.put(
        f"/api/role-projects/{project_id}/mistral-config",
        json={"secret_ref": None},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["secret_ref"] is None
    assert body["status"] == "not-configured"
    assert captured["secret_ref"] is None


# ---------------------------------------------------------------------------
# T7 — PUT projet inexistant (update lève ValueError) → 404
# ---------------------------------------------------------------------------


def test_put_mistral_config_project_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PUT /api/role-projects/{id}/mistral-config → 404 si update_mistral_secret_ref lève ValueError."""
    from role_builder.routes import mistral_config as route

    project_id = uuid4()

    async def fake_update(rp_id: UUID, secret_ref: str | None, *, pool: Any) -> None:
        raise ValueError(f"role_project {rp_id} not found")

    monkeypatch.setattr(route.role_projects, "update_mistral_secret_ref", fake_update)

    resp = client.put(
        f"/api/role-projects/{project_id}/mistral-config",
        json={"secret_ref": "some-ref"},
    )
    assert resp.status_code == 404, resp.text
    assert "not found" in resp.json()["detail"]
