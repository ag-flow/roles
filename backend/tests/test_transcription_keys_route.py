"""Tests pour routes.transcription_keys — CRUD + test + quota + usage."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers de fabrication de données fictives
# ---------------------------------------------------------------------------

_FIXED_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_FIXED_TENANT_ID = UUID("00000000-0000-0000-0000-000000000002")


def _make_key_row(
    key_id: UUID | None = None,
    provider: str = "deepgram",
    status: str = "active",
    monthly_cap_usd: float | None = 100.0,
    current_month_spend_usd: float = 0.0,
    current_balance_usd: float | None = 50.0,
    is_primary: bool = False,
    is_fallback: bool = False,
    workers_count: int = 1,
) -> dict[str, Any]:
    """Construit un dict simulant une ligne de user_transcription_keys."""
    now = datetime.now(tz=UTC)
    return {
        "id": key_id or uuid4(),
        "tenant_id": _FIXED_TENANT_ID,
        "user_id": _FIXED_USER_ID,
        "provider": provider,
        "label": "Ma clé Deepgram",
        "openbao_path": f"transcription-keys/{_FIXED_TENANT_ID}/{provider}/{key_id or uuid4()}",
        "status": status,
        "is_primary": is_primary,
        "is_fallback": is_fallback,
        "workers_count": workers_count,
        "monthly_cap_usd": monthly_cap_usd,
        "current_month_spend_usd": current_month_spend_usd,
        "current_balance_usd": current_balance_usd,
        "last_balance_check_at": now,
        "last_validated_at": now,
        "created_at": now,
        "updated_at": now,
    }


class _FakeOpenBao:
    """Stub OpenBaoClient pour les tests."""

    def __init__(
        self,
        secret_data: dict[str, Any] | None = None,
        *,
        record_calls: dict[str, Any] | None = None,
    ) -> None:
        self._secret_data = secret_data
        self._calls = record_calls if record_calls is not None else {}

    async def put(self, path: str, data: dict[str, Any]) -> None:
        self._calls["put_path"] = path
        self._calls["put_data"] = data

    async def get(self, path: str) -> dict[str, Any] | None:
        return self._secret_data

    async def delete(self, path: str) -> None:
        self._calls["delete_path"] = path

    async def aclose(self) -> None:
        pass


# ---------------------------------------------------------------------------
# T1 — GET /transcription-keys → 200 + liste
# ---------------------------------------------------------------------------


def test_list_keys_returns_200_and_list(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/transcription-keys → 200 + list[TranscriptionKeyOut]."""
    from role_builder.routes import transcription_keys as route

    rows = [
        _make_key_row(provider="deepgram"),
        _make_key_row(provider="assemblyai"),
    ]

    async def fake_list(user_id: UUID, *, pool: Any) -> list[dict]:
        return rows

    monkeypatch.setattr(route.keys_helper, "list_keys_for_user", fake_list)

    resp = client.get("/api/transcription-keys")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 2
    assert body[0]["provider"] == "deepgram"
    assert body[1]["provider"] == "assemblyai"


# ---------------------------------------------------------------------------
# T2 — POST /transcription-keys OK → 201 + DTO
# ---------------------------------------------------------------------------


def test_create_key_returns_201_and_dto(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys → 201 + TranscriptionKeyOut si clé valide."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id, provider="deepgram")
    calls: dict[str, Any] = {}

    async def fake_validate(provider: str, api_key: str) -> dict[str, Any]:
        return {"valid": True, "error": None, "balance_usd": None}

    async def fake_insert(**kwargs: Any) -> UUID:
        return key_id

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_update_balance(
        k_id: UUID, *, balance_usd: Any, checked_at: Any, pool: Any
    ) -> None:
        calls["update_balance_called"] = True

    monkeypatch.setattr(route.transcription_validator, "validate_transcription_key", fake_validate)
    monkeypatch.setattr(route.keys_helper, "insert_transcription_key", fake_insert)
    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao(record_calls=calls))

    resp = client.post(
        "/api/transcription-keys",
        json={
            "provider": "deepgram",
            "label": "Ma clé Deepgram",
            "api_key": "dg_test_key_123",
            "workers_count": 1,
            "is_primary": False,
            "is_fallback": False,
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"] == str(key_id)
    assert body["provider"] == "deepgram"
    assert "put_path" in calls
    assert "transcription-keys/" in calls["put_path"]
    assert calls.get("update_balance_called") is None  # balance_usd=None → pas appelé


# ---------------------------------------------------------------------------
# T3 — POST /transcription-keys clé invalide → 400
# ---------------------------------------------------------------------------


def test_create_key_invalid_returns_400(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys → 400 si validate retourne valid=False."""
    from role_builder.routes import transcription_keys as route

    async def fake_validate(provider: str, api_key: str) -> dict[str, Any]:
        return {"valid": False, "error": "unauthorized: invalid api key", "balance_usd": None}

    monkeypatch.setattr(route.transcription_validator, "validate_transcription_key", fake_validate)

    resp = client.post(
        "/api/transcription-keys",
        json={"provider": "deepgram", "api_key": "bad_key"},
    )
    assert resp.status_code == 400, resp.text
    assert "unauthorized" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# T4 — POST /transcription-keys avec balance retournée → update_key_balance appelé
# ---------------------------------------------------------------------------


def test_create_key_with_balance_calls_update_balance(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys → update_key_balance appelé si balance_usd présent."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id, current_balance_usd=42.5)
    calls: dict[str, Any] = {}

    async def fake_validate(provider: str, api_key: str) -> dict[str, Any]:
        return {"valid": True, "error": None, "balance_usd": 42.5}

    async def fake_insert(**kwargs: Any) -> UUID:
        return key_id

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_update_balance(
        k_id: UUID, *, balance_usd: Any, checked_at: Any, pool: Any
    ) -> None:
        calls["balance_usd"] = balance_usd

    monkeypatch.setattr(route.transcription_validator, "validate_transcription_key", fake_validate)
    monkeypatch.setattr(route.keys_helper, "insert_transcription_key", fake_insert)
    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "update_key_balance", fake_update_balance)
    monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao())

    resp = client.post(
        "/api/transcription-keys",
        json={"provider": "deepgram", "api_key": "dg_valid"},
    )
    assert resp.status_code == 201, resp.text
    assert calls.get("balance_usd") == 42.5


# ---------------------------------------------------------------------------
# T5 — PATCH /transcription-keys/{id} workers_count → 200 + update appelé
# ---------------------------------------------------------------------------


def test_update_key_workers_count(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /api/transcription-keys/{id} → 200 + update_key_settings appelé avec workers_count."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id, workers_count=3)
    calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_update(k_id: UUID, *, pool: Any, **kwargs: Any) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "update_key_settings", fake_update)

    resp = client.patch(
        f"/api/transcription-keys/{key_id}",
        json={"workers_count": 3},
    )
    assert resp.status_code == 200, resp.text
    assert calls.get("workers_count") == 3
    assert "is_primary" not in calls
    assert "is_fallback" not in calls


# ---------------------------------------------------------------------------
# T6 — PATCH /transcription-keys/{id} key not found → 404
# ---------------------------------------------------------------------------


def test_update_key_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /api/transcription-keys/{id} → 404 si clé inconnue."""
    from role_builder.routes import transcription_keys as route

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)

    resp = client.patch(
        f"/api/transcription-keys/{uuid4()}",
        json={"workers_count": 2},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "key not found"


# ---------------------------------------------------------------------------
# T7 — POST /transcription-keys/{id}/test valid → 200 + status=active
# ---------------------------------------------------------------------------


def test_test_key_valid_returns_active(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys/{id}/test → 200 + status=active si clé OK."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id)
    db_calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_validate(provider: str, api_key: str) -> dict[str, Any]:
        return {"valid": True, "error": None, "balance_usd": None}

    async def fake_update_balance(
        k_id: UUID, *, balance_usd: Any, checked_at: Any, pool: Any
    ) -> None:
        db_calls["balance_updated"] = True

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.transcription_validator, "validate_transcription_key", fake_validate)
    monkeypatch.setattr(route.keys_helper, "update_key_balance", fake_update_balance)

    # Mock pool.acquire pour le UPDATE inline status='active'
    from unittest.mock import AsyncMock, MagicMock

    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_acquire = MagicMock()
    mock_acquire.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_acquire.__aexit__ = AsyncMock(return_value=None)
    monkeypatch.setattr(route.db_pool.pool, "acquire", lambda: mock_acquire)

    monkeypatch.setattr(
        route, "OpenBaoClient", lambda: _FakeOpenBao(secret_data={"api_key": "dg_valid"})
    )

    resp = client.post(f"/api/transcription-keys/{key_id}/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["error"] is None


# ---------------------------------------------------------------------------
# T8 — POST /test invalid → 200 + status=invalid + mark_invalid appelé
# ---------------------------------------------------------------------------


def test_test_key_invalid_calls_mark_invalid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys/{id}/test → status=invalid + mark_invalid appelé."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id)
    calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_validate(provider: str, api_key: str) -> dict[str, Any]:
        return {"valid": False, "error": "unauthorized", "balance_usd": None}

    async def fake_mark_invalid(k_id: UUID, *, pool: Any) -> None:
        calls["mark_invalid_called"] = True
        calls["key_id"] = k_id

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.transcription_validator, "validate_transcription_key", fake_validate)
    monkeypatch.setattr(route.keys_helper, "mark_invalid", fake_mark_invalid)
    monkeypatch.setattr(
        route, "OpenBaoClient", lambda: _FakeOpenBao(secret_data={"api_key": "bad"})
    )

    resp = client.post(f"/api/transcription-keys/{key_id}/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "invalid"
    assert calls.get("mark_invalid_called") is True
    assert calls["key_id"] == key_id


# ---------------------------------------------------------------------------
# T9 — POST /test secret missing from OpenBao → 200 + status=invalid + error
# ---------------------------------------------------------------------------


def test_test_key_missing_secret_returns_invalid(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """POST /api/transcription-keys/{id}/test → status=invalid si secret absent d'OpenBao."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id)
    calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_mark_invalid(k_id: UUID, *, pool: Any) -> None:
        calls["mark_invalid_called"] = True

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "mark_invalid", fake_mark_invalid)
    # OpenBao retourne None (secret absent)
    monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao(secret_data=None))

    resp = client.post(f"/api/transcription-keys/{key_id}/test")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "invalid"
    assert "OpenBao" in body["error"]
    assert calls.get("mark_invalid_called") is True


# ---------------------------------------------------------------------------
# T10 — PATCH /transcription-keys/{id}/quota → 200 + update_key_settings appelé
# ---------------------------------------------------------------------------


def test_update_quota_calls_update_settings(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PATCH /api/transcription-keys/{id}/quota → 200 + update_key_settings(monthly_cap_usd)."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id, monthly_cap_usd=200.0)
    calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_update(k_id: UUID, *, pool: Any, **kwargs: Any) -> None:
        calls.update(kwargs)

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "update_key_settings", fake_update)

    resp = client.patch(
        f"/api/transcription-keys/{key_id}/quota",
        json={"monthly_cap_usd": 200.0},
    )
    assert resp.status_code == 200, resp.text
    assert calls.get("monthly_cap_usd") == 200.0


# ---------------------------------------------------------------------------
# T11 — GET /transcription-keys/{id}/usage avec cap → pct_used calculé
# ---------------------------------------------------------------------------


def test_get_usage_with_cap_returns_pct(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/transcription-keys/{id}/usage → pct_used=20.0 si spend=20/cap=100."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(
        key_id=key_id,
        monthly_cap_usd=100.0,
        current_month_spend_usd=20.0,
    )

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)

    resp = client.get(f"/api/transcription-keys/{key_id}/usage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["current_month_spend_usd"] == 20.0
    assert body["monthly_cap_usd"] == 100.0
    assert body["pct_used"] == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# T12 — GET /usage sans cap → pct_used=None
# ---------------------------------------------------------------------------


def test_get_usage_without_cap_returns_none_pct(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /api/transcription-keys/{id}/usage → pct_used=None si pas de cap."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(
        key_id=key_id,
        monthly_cap_usd=None,
        current_month_spend_usd=15.0,
    )

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)

    resp = client.get(f"/api/transcription-keys/{key_id}/usage")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pct_used"] is None


# ---------------------------------------------------------------------------
# T13 — DELETE /transcription-keys/{id} OK → 204 + OpenBao.delete + delete_key
# ---------------------------------------------------------------------------


def test_delete_key_returns_204_and_cleans_up(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /api/transcription-keys/{id} → 204 + OpenBao.delete + delete_key appelés."""
    from role_builder.routes import transcription_keys as route

    key_id = uuid4()
    key_row = _make_key_row(key_id=key_id)
    calls: dict[str, Any] = {}

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> dict[str, Any]:
        return key_row

    async def fake_delete(k_id: UUID, *, pool: Any) -> None:
        calls["deleted_id"] = k_id

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)
    monkeypatch.setattr(route.keys_helper, "delete_key", fake_delete)
    monkeypatch.setattr(route, "OpenBaoClient", lambda: _FakeOpenBao(record_calls=calls))

    resp = client.delete(f"/api/transcription-keys/{key_id}")
    assert resp.status_code == 204, resp.text
    assert calls.get("deleted_id") == key_id
    assert "delete_path" in calls


# ---------------------------------------------------------------------------
# T14 — DELETE /transcription-keys/{id} not found → 404
# ---------------------------------------------------------------------------


def test_delete_key_not_found_returns_404(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DELETE /api/transcription-keys/{id} → 404 si clé inconnue."""
    from role_builder.routes import transcription_keys as route

    async def fake_get(k_id: UUID, *, user_id: UUID, pool: Any) -> None:
        return None

    monkeypatch.setattr(route.keys_helper, "get_key", fake_get)

    resp = client.delete(f"/api/transcription-keys/{uuid4()}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["detail"] == "key not found"
