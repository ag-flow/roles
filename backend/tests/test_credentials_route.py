"""Tests pour routes.credentials — CRUD credentials + intégration vault."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers de fabrication de données fictives
# ---------------------------------------------------------------------------


def _make_cred_row(
    cred_id: UUID | None = None,
    platform: str = "youtube",
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de la table user_credentials."""
    now = datetime.now(tz=UTC)
    return {
        "id": cred_id or uuid4(),
        "tenant_id": uuid4(),
        "user_id": user_id or uuid4(),
        "platform": platform,
        "label": "Mon compte YT",
        "vault_secret_name": f"users/tenant_at_example.com/scraping/youtube/{uuid4()}",
        "status": "active",
        "last_validated_at": now,
        "expires_at": None,
        "created_at": now,
        "updated_at": now,
    }


class _FakeUserVaultService:
    """Stub UserVaultService pour les tests (write/read/try_delete no-op)."""

    def __init__(self, cookies_b64: str | None = None) -> None:
        self._cookies_b64 = cookies_b64

    async def write(self, secret_name: str, value: str) -> None:
        pass

    async def read(self, secret_name: str) -> str | None:
        return self._cookies_b64

    async def try_delete(self, secret_name: str) -> None:
        pass


# ---------------------------------------------------------------------------
# T1 — GET /credentials → 200 + liste
# ---------------------------------------------------------------------------


def test_list_credentials_returns_user_credentials(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/credentials → 200 + list[UserCredentialOut]."""
    from role_builder.routes import credentials as route

    rows = [_make_cred_row(platform="youtube"), _make_cred_row(platform="instagram")]

    async def fake_list(*, user_id: UUID, platform: str | None, pool: Any) -> list[dict]:
        return rows

    monkeypatch.setattr(route.creds_helper, "list_credentials", fake_list)

    resp = client.get("/api/credentials")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["platform"] == "youtube"
    assert body[1]["platform"] == "instagram"


# ---------------------------------------------------------------------------
# T2 — GET /credentials?platform=youtube → platform est bien transmis
# ---------------------------------------------------------------------------


def test_list_credentials_passes_platform_filter(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/credentials?platform=youtube → platform passé au helper."""
    from role_builder.routes import credentials as route

    captured: dict[str, Any] = {}

    async def fake_list(*, user_id: UUID, platform: str | None, pool: Any) -> list[dict]:
        captured["platform"] = platform
        return [_make_cred_row(platform="youtube")]

    monkeypatch.setattr(route.creds_helper, "list_credentials", fake_list)

    resp = client.get("/api/credentials?platform=youtube")
    assert resp.status_code == 200, resp.text
    assert captured["platform"] == "youtube"


# ---------------------------------------------------------------------------
# T3 — POST /credentials OK → 201 + DTO
# ---------------------------------------------------------------------------


def test_create_credential_returns_201_and_dto(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/credentials → 201 + UserCredentialOut si cookies valides."""
    from role_builder.routes import credentials as route

    cred_id = uuid4()
    cred_row = _make_cred_row(cred_id=cred_id, platform="youtube")

    async def fake_validate(platform: str, cookies_b64: str) -> dict[str, Any]:
        return {"valid": True, "error": None, "expires_at": None, "cookies_count": 3}

    async def fake_insert(
        *,
        tenant_id: UUID,
        user_id: UUID,
        platform: str,
        label: str | None,
        vault_secret_name: str,
        status: str,
        last_validated_at: Any,
        expires_at: Any,
        pool: Any,
    ) -> UUID:
        return cred_id

    async def fake_get(c_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return cred_row

    monkeypatch.setattr(route.credentials_validator, "validate_cookies", fake_validate)
    monkeypatch.setattr(route.creds_helper, "insert_user_credential", fake_insert)
    monkeypatch.setattr(route.creds_helper, "get_credential", fake_get)
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeUserVaultService())

    resp = client.post(
        "/api/credentials",
        json={"platform": "youtube", "label": "Mon compte YT", "cookies_b64": "dGVzdA=="},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(cred_id)
    assert body["platform"] == "youtube"
    assert body["status"] == "active"


# ---------------------------------------------------------------------------
# T4 — POST /credentials cookies invalides → 400
# ---------------------------------------------------------------------------


def test_create_credential_invalid_cookies_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/credentials → 400 si validate_cookies retourne valid=False."""
    from role_builder.routes import credentials as route

    async def fake_validate(platform: str, cookies_b64: str) -> dict[str, Any]:
        return {
            "valid": False,
            "error": "missing required cookies for youtube",
            "expires_at": None,
            "cookies_count": 0,
        }

    monkeypatch.setattr(route.credentials_validator, "validate_cookies", fake_validate)

    resp = client.post(
        "/api/credentials",
        json={"platform": "youtube", "label": None, "cookies_b64": "aW52YWxpZA=="},
    )
    assert resp.status_code == 400, resp.text
    assert "missing required cookies" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# T5 — POST /credentials/{id}/test OK → 200 + status=active
# ---------------------------------------------------------------------------


def test_test_credential_returns_active(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/credentials/{id}/test → 200 + status=active si cookies OK."""
    from role_builder.routes import credentials as route

    cred_id = uuid4()
    cred_row = _make_cred_row(cred_id=cred_id, platform="youtube")
    captured: dict[str, Any] = {}

    async def fake_get(c_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return cred_row

    async def fake_validate(platform: str, cookies_b64: str) -> dict[str, Any]:
        return {"valid": True, "error": None, "expires_at": None, "cookies_count": 3}

    async def fake_update(c_id: UUID, *, status: str, last_validated_at: Any, pool: Any) -> None:
        captured["status"] = status

    monkeypatch.setattr(route.creds_helper, "get_credential", fake_get)
    monkeypatch.setattr(route.credentials_validator, "validate_cookies", fake_validate)
    monkeypatch.setattr(route.creds_helper, "update_credential_status", fake_update)
    monkeypatch.setattr(
        route,
        "_get_vault_service",
        lambda: _FakeUserVaultService(cookies_b64="dGVzdA=="),
    )

    resp = client.post(f"/api/credentials/{cred_id}/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["error"] is None
    assert captured["status"] == "active"


# ---------------------------------------------------------------------------
# T6 — POST /credentials/{id}/test credential not found → 404
# ---------------------------------------------------------------------------


def test_test_credential_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/credentials/{id}/test → 404 si credential inconnu."""
    from role_builder.routes import credentials as route

    cred_id = uuid4()

    async def fake_get(c_id: UUID, *, user_id: UUID, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.creds_helper, "get_credential", fake_get)

    resp = client.post(f"/api/credentials/{cred_id}/test")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "credential not found"


# ---------------------------------------------------------------------------
# T7 — DELETE /credentials/{id} OK → 204
# ---------------------------------------------------------------------------


def test_delete_credential_returns_204(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /api/credentials/{id} → 204 si credential existe."""
    from role_builder.routes import credentials as route

    cred_id = uuid4()
    cred_row = _make_cred_row(cred_id=cred_id)
    captured: dict[str, Any] = {}

    async def fake_get(c_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return cred_row

    async def fake_delete(c_id: UUID, *, pool: Any) -> None:
        captured["deleted_id"] = c_id

    monkeypatch.setattr(route.creds_helper, "get_credential", fake_get)
    monkeypatch.setattr(route.creds_helper, "delete_credential", fake_delete)
    monkeypatch.setattr(route, "_get_vault_service", lambda: _FakeUserVaultService())

    resp = client.delete(f"/api/credentials/{cred_id}")
    assert resp.status_code == 204, resp.text
    assert captured["deleted_id"] == cred_id


# ---------------------------------------------------------------------------
# T8 — DELETE /credentials/{id} not found → 404
# ---------------------------------------------------------------------------


def test_delete_credential_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /api/credentials/{id} → 404 si credential inconnu."""
    from role_builder.routes import credentials as route

    cred_id = uuid4()

    async def fake_get(c_id: UUID, *, user_id: UUID, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.creds_helper, "get_credential", fake_get)

    resp = client.delete(f"/api/credentials/{cred_id}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "credential not found"
