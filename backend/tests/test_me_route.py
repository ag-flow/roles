"""Tests for GET /api/me — retourne le user courant via get_current_user."""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_local_app() -> FastAPI:
    """Build a minimal FastAPI app that mounts only the /me router.

    A4 tests do not yet rely on the main app cabling (that lands in A7).
    """
    from role_builder.routes import me

    app = FastAPI()
    app.include_router(me.router, prefix="/api", tags=["auth"])
    return app


def test_get_me_with_disabled_auth_returns_default_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avec disable_auth=True, GET /api/me renvoie le stub."""
    from role_builder.config import TENANT_ID_DEFAULT, settings

    monkeypatch.setattr(settings, "disable_auth", True, raising=False)
    client = TestClient(_make_local_app())

    resp = client.get("/api/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["username"] == "dev-disabled-auth"
    assert body["tenant_id"] == str(TENANT_ID_DEFAULT)
    assert body["user_id"] == "00000000-0000-0000-0000-000000000001"
    assert body["email"] is None


def test_get_me_without_header_when_auth_enabled_returns_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si disable_auth=False et pas de header Authorization → 401."""
    from role_builder.config import settings

    monkeypatch.setattr(settings, "disable_auth", False, raising=False)
    client = TestClient(_make_local_app())

    resp = client.get("/api/me")
    assert resp.status_code == 401, resp.text
