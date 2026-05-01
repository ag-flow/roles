"""Tests routes /api/auth/github/* — Sprint 8."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def test_start_returns_authorize_url_and_stores_state(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/auth/github/start retourne une URL GitHub avec state."""
    from role_builder.routes import github_auth as route

    insert_calls: list[dict[str, Any]] = []

    async def fake_insert_state(
        *, state: str, user_id: UUID, tenant_id: UUID, ttl_seconds: int,
        pool: Any, provider: str = "github",
    ) -> None:
        insert_calls.append(
            {"state": state, "user_id": user_id, "ttl": ttl_seconds},
        )

    monkeypatch.setattr(route.oauth_states, "insert_state", fake_insert_state)

    resp = client.get("/api/auth/github/start")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "redirect_url" in body
    assert body["redirect_url"].startswith(
        "https://github.com/login/oauth/authorize?",
    )
    assert "state=" in body["redirect_url"]
    assert "client_id=" in body["redirect_url"]
    assert "scope=public_repo" in body["redirect_url"]
    assert len(insert_calls) == 1
    assert insert_calls[0]["ttl"] == 600


def test_callback_with_invalid_state_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_consume(state: str, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.oauth_states, "consume_state", fake_consume)

    resp = client.get("/api/auth/github/callback", params={"code": "x", "state": "bad"})
    assert resp.status_code == 400


def test_callback_full_flow_stores_token_and_returns_login(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route
    from role_builder.services.openbao_client import OpenBaoClient

    user_id = uuid4()
    tenant_id = uuid4()

    async def fake_consume(state: str, *, pool: Any) -> Any:
        return {"user_id": user_id, "tenant_id": tenant_id, "expires_at": None}

    async def fake_exchange(self: Any, code: str) -> str:
        assert code == "github-code"
        return "ghp_secret"

    async def fake_user_info(self: Any, token: str) -> dict[str, Any]:
        assert token == "ghp_secret"
        return {"login": "alice", "id": 42}

    openbao_calls: list[tuple[str, dict[str, str]]] = []

    async def fake_put(self: Any, path: str, data: dict[str, str]) -> None:
        openbao_calls.append((path, data))

    async def fake_aclose(self: Any) -> None:
        return None

    upsert_calls: list[dict[str, Any]] = []

    async def fake_upsert(**kwargs: Any) -> None:
        upsert_calls.append(kwargs)

    monkeypatch.setattr(route.oauth_states, "consume_state", fake_consume)
    monkeypatch.setattr(
        route.gh_oauth_module.gh_oauth.__class__, "exchange_code", fake_exchange,
    )
    monkeypatch.setattr(
        route.gh_oauth_module.gh_oauth.__class__, "get_user_info", fake_user_info,
    )
    monkeypatch.setattr(OpenBaoClient, "put", fake_put)
    monkeypatch.setattr(OpenBaoClient, "aclose", fake_aclose)
    monkeypatch.setattr(route.github_integrations, "upsert", fake_upsert)

    resp = client.get(
        "/api/auth/github/callback",
        params={"code": "github-code", "state": "good"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"status": "connected", "github_login": "alice"}

    # Token stocké en OpenBao
    assert len(openbao_calls) == 1
    assert "github-tokens" in openbao_calls[0][0]
    assert openbao_calls[0][1] == {"access_token": "ghp_secret"}

    # Integration upsertée
    assert len(upsert_calls) == 1
    assert upsert_calls[0]["github_login"] == "alice"
    assert upsert_calls[0]["github_user_id"] == 42


def test_status_returns_connected_when_integration_exists(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(user_id: UUID, *, pool: Any) -> Any:
        return {
            "github_login": "alice",
            "scope": "public_repo",
            "last_validated_at": None,
        }

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/auth/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is True
    assert body["github_login"] == "alice"
    assert body["scope"] == "public_repo"


def test_status_returns_not_connected_when_absent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(user_id: UUID, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_user_id", fake_get)

    resp = client.get("/api/auth/github/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["connected"] is False
    assert body["github_login"] is None


def test_disconnect_when_not_connected_returns_not_connected_status(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_list(user_id: UUID, *, pool: Any) -> list[Any]:
        return []

    monkeypatch.setattr(route.github_integrations, "list_by_user_id", fake_list)

    resp = client.delete("/api/auth/github")
    assert resp.status_code == 200
    assert resp.json() == {"status": "not-connected"}


def test_disconnect_removes_token_and_integration(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase 2 D : disconnect supprime TOUTES les intégrations du user."""
    from role_builder.routes import github_auth as route
    from role_builder.services.openbao_client import OpenBaoClient

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict[str, Any]]:
        return [
            {"openbao_path": "github-tokens/t/u-perso"},
            {"openbao_path": "github-tokens/t/u-org"},
        ]

    deleted_paths: list[str] = []

    async def fake_delete_token(self: Any, path: str) -> None:
        deleted_paths.append(path)

    async def fake_aclose(self: Any) -> None:
        return None

    deleted_users: list[UUID] = []

    async def fake_delete_integration(user_id: UUID, *, pool: Any) -> int:
        deleted_users.append(user_id)
        return 2

    monkeypatch.setattr(route.github_integrations, "list_by_user_id", fake_list)
    monkeypatch.setattr(OpenBaoClient, "delete", fake_delete_token)
    monkeypatch.setattr(OpenBaoClient, "aclose", fake_aclose)
    monkeypatch.setattr(
        route.github_integrations, "delete_by_user_id", fake_delete_integration,
    )

    resp = client.delete("/api/auth/github")
    assert resp.status_code == 200
    assert resp.json() == {"status": "disconnected"}
    assert deleted_paths == [
        "github-tokens/t/u-perso", "github-tokens/t/u-org",
    ]
    assert len(deleted_users) == 1


# ---------------------------------------------------------------------------
# Phase 2 D : nouvelles routes multi-comptes
# ---------------------------------------------------------------------------


def test_list_integrations_returns_all(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime

    from role_builder.routes import github_auth as route

    now = datetime.now(tz=UTC)
    fake_rows = [
        {
            "id": uuid4(), "user_id": uuid4(), "tenant_id": uuid4(),
            "github_login": "alice", "github_user_id": 1,
            "openbao_path": "p1", "scope": "public_repo",
            "last_validated_at": now, "created_at": now,
        },
        {
            "id": uuid4(), "user_id": uuid4(), "tenant_id": uuid4(),
            "github_login": "alice-org", "github_user_id": 2,
            "openbao_path": "p2", "scope": "public_repo",
            "last_validated_at": now, "created_at": now,
        },
    ]

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict[str, Any]]:
        return fake_rows

    monkeypatch.setattr(route.github_integrations, "list_by_user_id", fake_list)

    resp = client.get("/api/auth/github/integrations")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    logins = {item["github_login"] for item in body}
    assert logins == {"alice", "alice-org"}


def test_list_integrations_returns_empty_when_none(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_list(user_id: UUID, *, pool: Any) -> list[Any]:
        return []

    monkeypatch.setattr(route.github_integrations, "list_by_user_id", fake_list)

    resp = client.get("/api/auth/github/integrations")
    assert resp.status_code == 200
    assert resp.json() == []


def test_delete_integration_removes_token_and_row(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route
    from role_builder.services.openbao_client import OpenBaoClient

    fixed_user_id = UUID("00000000-0000-0000-0000-000000000001")
    integration_id = uuid4()

    async def fake_get(iid: UUID, *, pool: Any) -> dict[str, Any]:
        return {
            "id": iid, "user_id": fixed_user_id,
            "openbao_path": "github-tokens/t/spec",
            "github_login": "alice",
        }

    deleted_paths: list[str] = []

    async def fake_delete_token(self: Any, path: str) -> None:
        deleted_paths.append(path)

    async def fake_aclose(self: Any) -> None:
        return None

    delete_calls: list[UUID] = []

    async def fake_delete_by_id(iid: UUID, *, pool: Any) -> int:
        delete_calls.append(iid)
        return 1

    monkeypatch.setattr(route.github_integrations, "get_by_id", fake_get)
    monkeypatch.setattr(route.github_integrations, "delete_by_id", fake_delete_by_id)
    monkeypatch.setattr(OpenBaoClient, "delete", fake_delete_token)
    monkeypatch.setattr(OpenBaoClient, "aclose", fake_aclose)

    resp = client.delete(f"/api/auth/github/integrations/{integration_id}")
    assert resp.status_code == 204, resp.text
    assert deleted_paths == ["github-tokens/t/spec"]
    assert delete_calls == [integration_id]


def test_delete_integration_returns_404_when_unknown(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    async def fake_get(iid: UUID, *, pool: Any) -> Any:
        return None

    monkeypatch.setattr(route.github_integrations, "get_by_id", fake_get)
    resp = client.delete(f"/api/auth/github/integrations/{uuid4()}")
    assert resp.status_code == 404


def test_delete_integration_returns_403_when_not_owner(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.routes import github_auth as route

    other_user = uuid4()  # ≠ fixé du conftest

    async def fake_get(iid: UUID, *, pool: Any) -> dict[str, Any]:
        return {
            "id": iid, "user_id": other_user, "openbao_path": "p",
            "github_login": "x",
        }

    monkeypatch.setattr(route.github_integrations, "get_by_id", fake_get)
    resp = client.delete(f"/api/auth/github/integrations/{uuid4()}")
    assert resp.status_code == 403
