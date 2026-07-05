"""Tests pour routes.wallets — CRUD wallets Harpocrate par utilisateur."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from role_builder.services.secret_store import InvalidWalletTokenError

# ---------------------------------------------------------------------------
# Fabrique de données + fake store
# ---------------------------------------------------------------------------


def _make_wallet_row(wallet_id: UUID | None = None) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    return {
        "id": wallet_id or uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "label": "Mon wallet",
        "api_url": "https://vault.yoops.org",
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


class _FakeStore:
    def __init__(self) -> None:
        self.registered: list[dict[str, Any]] = []
        self.invalidated: list[UUID] = []
        self.register_error: Exception | None = None
        self.register_return: UUID = uuid4()

    async def register_wallet(self, **kwargs: Any) -> UUID:
        if self.register_error is not None:
            raise self.register_error
        self.registered.append(kwargs)
        return self.register_return

    def invalidate_wallet(self, wallet_id: UUID) -> None:
        self.invalidated.append(wallet_id)


@pytest.fixture()
def fake_store(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    from role_builder.routes import wallets as route

    store = _FakeStore()
    monkeypatch.setattr(route, "_get_secret_store", lambda: store)
    return store


# ---------------------------------------------------------------------------
# GET /api/wallets
# ---------------------------------------------------------------------------


def test_list_wallets_returns_wallets_without_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.routes import wallets as route

    rows = [_make_wallet_row(), _make_wallet_row()]

    async def fake_list(*, user_id: UUID, pool: Any) -> list[dict]:
        return rows

    monkeypatch.setattr(route.wallets_helper, "list_wallets", fake_list)

    resp = client.get("/api/wallets")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["label"] == "Mon wallet"
    assert "api_token" not in body[0]
    assert "api_token_encrypted" not in body[0]


# ---------------------------------------------------------------------------
# POST /api/wallets
# ---------------------------------------------------------------------------


def test_create_wallet_registers_and_returns_dto(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import wallets as route

    wallet_row = _make_wallet_row(fake_store.register_return)

    async def fake_get(*, wallet_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return wallet_row

    monkeypatch.setattr(route.wallets_helper, "get_wallet", fake_get)

    resp = client.post(
        "/api/wallets",
        json={"label": "Mon wallet", "api_token": "hrpv_1_abc"},
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["id"] == str(fake_store.register_return)
    assert len(fake_store.registered) == 1
    assert fake_store.registered[0]["token"] == "hrpv_1_abc"
    # URL par défaut si non fournie
    assert fake_store.registered[0]["api_url"] == "https://vault.yoops.org"


def test_create_wallet_invalid_token_returns_400(
    client: TestClient, fake_store: _FakeStore
) -> None:
    fake_store.register_error = InvalidWalletTokenError("token refusé")

    resp = client.post(
        "/api/wallets",
        json={"label": "x", "api_token": "pas-un-token"},
    )
    assert resp.status_code == 400
    assert "token" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# DELETE /api/wallets/{id}
# ---------------------------------------------------------------------------


def test_delete_wallet_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import wallets as route

    wallet_row = _make_wallet_row()

    async def fake_get(*, wallet_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return wallet_row

    async def fake_count(*, wallet_id: UUID, pool: Any) -> int:
        return 0

    async def fake_delete(*, wallet_id: UUID, user_id: UUID, pool: Any) -> bool:
        return True

    monkeypatch.setattr(route.wallets_helper, "get_wallet", fake_get)
    monkeypatch.setattr(route.wallets_helper, "count_secrets_for_wallet", fake_count)
    monkeypatch.setattr(route.wallets_helper, "delete_wallet", fake_delete)

    resp = client.delete(f"/api/wallets/{wallet_row['id']}")
    assert resp.status_code == 204
    assert fake_store.invalidated == [wallet_row["id"]]


def test_delete_wallet_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import wallets as route

    async def fake_get(*, wallet_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return None

    monkeypatch.setattr(route.wallets_helper, "get_wallet", fake_get)

    resp = client.delete(f"/api/wallets/{uuid4()}")
    assert resp.status_code == 404


def test_delete_wallet_with_secrets_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import wallets as route

    wallet_row = _make_wallet_row()

    async def fake_get(*, wallet_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return wallet_row

    async def fake_count(*, wallet_id: UUID, pool: Any) -> int:
        return 2

    monkeypatch.setattr(route.wallets_helper, "get_wallet", fake_get)
    monkeypatch.setattr(route.wallets_helper, "count_secrets_for_wallet", fake_count)

    resp = client.delete(f"/api/wallets/{wallet_row['id']}")
    assert resp.status_code == 409
    assert fake_store.invalidated == []
