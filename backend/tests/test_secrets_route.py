"""Tests pour routes.user_secrets — saisie/liste/suppression des secrets typés."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from role_builder.services.secret_store import UnknownWalletError

# ---------------------------------------------------------------------------
# Fabrique de données + fake store
# ---------------------------------------------------------------------------


def _make_secret_row(
    secret_id: UUID | None = None,
    storage: str = "local",
    secret_type: str = "openai-whisper",
) -> dict[str, Any]:
    now = datetime.now(tz=UTC)
    wallet = storage == "wallet"
    return {
        "id": secret_id or uuid4(),
        "tenant_id": uuid4(),
        "user_id": uuid4(),
        "secret_type": secret_type,
        "label": "Ma clé",
        "storage": storage,
        "value_encrypted": None if wallet else b"fernet",
        "wallet_id": uuid4() if wallet else None,
        "wallet_path": f"roles/{secret_type}/x" if wallet else None,
        "status": "active",
        "created_at": now,
        "updated_at": now,
    }


class _FakeStore:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.deleted: list[dict[str, Any]] = []
        self.create_error: Exception | None = None
        self.create_return: UUID = uuid4()

    async def create_secret(self, **kwargs: Any) -> UUID:
        if self.create_error is not None:
            raise self.create_error
        self.created.append(kwargs)
        return self.create_return

    async def delete_secret(self, secret: dict[str, Any], *, pool: Any) -> None:
        self.deleted.append(secret)


@pytest.fixture()
def fake_store(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> _FakeStore:
    from role_builder.routes import user_secrets as route

    store = _FakeStore()
    monkeypatch.setattr(route, "_get_secret_store", lambda: store)
    return store


# ---------------------------------------------------------------------------
# GET /api/secrets
# ---------------------------------------------------------------------------


def test_list_secrets_never_exposes_values(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.routes import user_secrets as route

    rows = [_make_secret_row(), _make_secret_row(storage="wallet", secret_type="deepgram")]

    async def fake_list(
        *, user_id: UUID, secret_type: str | None = None, pool: Any
    ) -> list[dict]:
        return [{k: v for k, v in r.items() if k != "value_encrypted"} for r in rows]

    monkeypatch.setattr(route.secrets_helper, "list_secrets", fake_list)

    resp = client.get("/api/secrets")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    for item in body:
        assert "value" not in item
        assert "value_encrypted" not in item
        assert "wallet_path" not in item
    assert body[0]["storage"] == "local"
    assert body[1]["storage"] == "wallet"


def test_list_secrets_filters_by_type(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.routes import user_secrets as route

    captured: dict[str, Any] = {}

    async def fake_list(
        *, user_id: UUID, secret_type: str | None = None, pool: Any
    ) -> list[dict]:
        captured["secret_type"] = secret_type
        return []

    monkeypatch.setattr(route.secrets_helper, "list_secrets", fake_list)

    resp = client.get("/api/secrets?secret_type=deepgram")
    assert resp.status_code == 200
    assert captured["secret_type"] == "deepgram"


# ---------------------------------------------------------------------------
# POST /api/secrets
# ---------------------------------------------------------------------------


def test_create_local_secret(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import user_secrets as route

    row = _make_secret_row(fake_store.create_return)

    async def fake_get(*, secret_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return row

    monkeypatch.setattr(route.secrets_helper, "get_secret", fake_get)

    resp = client.post(
        "/api/secrets",
        json={"secret_type": "openai-whisper", "label": "Ma clé", "value": "sk-abc"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(fake_store.create_return)
    assert "value" not in body
    assert len(fake_store.created) == 1
    assert fake_store.created[0]["value"] == "sk-abc"
    assert fake_store.created[0]["wallet_id"] is None


def test_create_wallet_secret_passes_wallet_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import user_secrets as route

    wallet_id = uuid4()
    row = _make_secret_row(fake_store.create_return, storage="wallet")

    async def fake_get(*, secret_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return row

    monkeypatch.setattr(route.secrets_helper, "get_secret", fake_get)

    resp = client.post(
        "/api/secrets",
        json={
            "secret_type": "deepgram",
            "label": "Clé DG",
            "value": "dg-1",
            "wallet_id": str(wallet_id),
        },
    )
    assert resp.status_code == 201, resp.text
    assert fake_store.created[0]["wallet_id"] == wallet_id


def test_create_secret_unknown_wallet_returns_404(
    client: TestClient, fake_store: _FakeStore
) -> None:
    fake_store.create_error = UnknownWalletError("introuvable")

    resp = client.post(
        "/api/secrets",
        json={
            "secret_type": "deepgram",
            "label": "x",
            "value": "v",
            "wallet_id": str(uuid4()),
        },
    )
    assert resp.status_code == 404


def test_create_secret_rejects_unknown_type(client: TestClient) -> None:
    resp = client.post(
        "/api/secrets",
        json={"secret_type": "mistral", "label": "x", "value": "v"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/secrets/{id}
# ---------------------------------------------------------------------------


def test_delete_secret_ok(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import user_secrets as route

    row = _make_secret_row()

    async def fake_get(*, secret_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return row

    async def fake_count(*, secret_id: UUID, pool: Any) -> int:
        return 0

    monkeypatch.setattr(route.secrets_helper, "get_secret", fake_get)
    monkeypatch.setattr(route.secrets_helper, "count_service_references", fake_count)

    resp = client.delete(f"/api/secrets/{row['id']}")
    assert resp.status_code == 204
    assert fake_store.deleted == [row]


def test_delete_secret_not_found(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import user_secrets as route

    async def fake_get(*, secret_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return None

    monkeypatch.setattr(route.secrets_helper, "get_secret", fake_get)

    resp = client.delete(f"/api/secrets/{uuid4()}")
    assert resp.status_code == 404


def test_delete_secret_referenced_by_service_returns_409(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, fake_store: _FakeStore
) -> None:
    from role_builder.routes import user_secrets as route

    row = _make_secret_row()

    async def fake_get(*, secret_id: UUID, user_id: UUID, pool: Any) -> dict | None:
        return row

    async def fake_count(*, secret_id: UUID, pool: Any) -> int:
        return 1

    monkeypatch.setattr(route.secrets_helper, "get_secret", fake_get)
    monkeypatch.setattr(route.secrets_helper, "count_service_references", fake_count)

    resp = client.delete(f"/api/secrets/{row['id']}")
    assert resp.status_code == 409
    assert fake_store.deleted == []
