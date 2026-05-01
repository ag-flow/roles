"""Tests for routes.websocket — FastAPI WebSocket endpoint.

Inject a stub `WSRelay` (no real DB connection) into the singleton slot.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


class _StubRelay:
    """Behavioral subset of WSRelay sufficient for the WS route."""

    def __init__(self) -> None:
        self._queues: list[asyncio.Queue[dict[str, Any]]] = []

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def subscribe(self, *, tenant_id: UUID) -> asyncio.Queue[dict[str, Any]]:  # noqa: ARG002
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    async def fire(self, payload: dict[str, Any]) -> None:
        for q in list(self._queues):
            await q.put(payload)

    @property
    def subscriber_count(self) -> int:
        return len(self._queues)


@pytest.fixture()
def app_with_stub_relay(
    stubbed_env: None,  # noqa: ARG001
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Any, _StubRelay]:
    """Inject a stub relay into the singleton slot consumed by routes/websocket."""
    from role_builder import db as db_module
    from role_builder.config import settings as _settings
    from role_builder.main import app
    from role_builder.routes import websocket as ws_route_module
    from role_builder.services import ws_relay as ws_relay_module

    monkeypatch.setattr(_settings, "disable_orchestrator", True, raising=False)
    monkeypatch.setattr(_settings, "disable_ws_relay", True, raising=False)
    monkeypatch.setattr(_settings, "disable_worker_manager", True, raising=False)
    monkeypatch.setattr(_settings, "disable_chunking_worker", True, raising=False)
    monkeypatch.setattr(_settings, "disable_scheduler", True, raising=False)
    monkeypatch.setattr(_settings, "disable_auth", True, raising=False)
    monkeypatch.setattr(_settings, "disable_migrations", True, raising=False)

    class _StubPool:
        async def close(self) -> None:
            return None

    monkeypatch.setattr(db_module.db_pool, "_pool", _StubPool(), raising=False)

    stub = _StubRelay()
    monkeypatch.setattr(ws_relay_module, "ws_relay", stub)
    monkeypatch.setattr(ws_route_module, "ws_relay", stub)
    return app, stub


def test_ws_accepts_connection_and_forwards_event(
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    """Avec disable_auth=True, /ws accepte la connexion et tenant_id vient
    du _DISABLED_USER (TENANT_ID_DEFAULT)."""
    app, stub = app_with_stub_relay
    from role_builder.config import TENANT_ID_DEFAULT

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            event = {
                "channel": "source_items_changes",
                "payload": {
                    "table": "source_items",
                    "op": "UPDATE",
                    "tenant_id": str(TENANT_ID_DEFAULT),
                    "id": str(uuid4()),
                    "status": "audio_ready",
                },
            }
            ws.portal.call(stub.fire, event)
            received = ws.receive_json()
            assert received["channel"] == "source_items_changes"
            assert received["payload"]["status"] == "audio_ready"


def test_ws_disconnect_unsubscribes(
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    app, stub = app_with_stub_relay

    with TestClient(app) as client:
        with client.websocket_connect("/ws"):
            assert stub.subscriber_count == 1

    assert stub.subscriber_count == 0


def test_ws_rejects_missing_token_when_auth_enabled(
    monkeypatch: pytest.MonkeyPatch,
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    """disable_auth=False + pas de token → WS fermée immédiatement (1008)."""
    from role_builder.config import settings as _settings

    monkeypatch.setattr(_settings, "disable_auth", False, raising=False)
    app, _ = app_with_stub_relay

    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
        # Code 1008 (Policy Violation)
        assert exc_info.value.code == 1008


def test_ws_rejects_invalid_token(
    monkeypatch: pytest.MonkeyPatch,
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    """disable_auth=False + token invalide → WS fermée 1008."""
    from role_builder.auth import dependencies as auth_deps
    from role_builder.auth.keycloak import InvalidTokenError
    from role_builder.config import settings as _settings

    monkeypatch.setattr(_settings, "disable_auth", False, raising=False)

    class _BadValidator:
        async def validate(self, token: str) -> dict[str, Any]:
            raise InvalidTokenError("forged signature")

    monkeypatch.setattr(auth_deps, "_validator", _BadValidator())

    app, _ = app_with_stub_relay
    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/ws?token=bad-token") as ws:
                ws.receive_json()
        assert exc_info.value.code == 1008


def test_ws_accepts_valid_token(
    monkeypatch: pytest.MonkeyPatch,
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    """disable_auth=False + token valide → WS acceptée, tenant_id du user."""
    from role_builder.auth import dependencies as auth_deps
    from role_builder.config import TENANT_ID_DEFAULT
    from role_builder.config import settings as _settings

    monkeypatch.setattr(_settings, "disable_auth", False, raising=False)

    user_id = uuid4()

    class _GoodValidator:
        async def validate(self, token: str) -> dict[str, Any]:
            assert token == "valid-token"
            return {
                "sub": str(user_id),
                "preferred_username": "alice",
                "email": "alice@example.com",
            }

    monkeypatch.setattr(auth_deps, "_validator", _GoodValidator())

    app, stub = app_with_stub_relay
    with TestClient(app) as client:
        with client.websocket_connect("/ws?token=valid-token") as ws:
            assert stub.subscriber_count == 1
            event = {
                "channel": "runs_changes",
                "payload": {
                    "table": "runs",
                    "op": "UPDATE",
                    "tenant_id": str(TENANT_ID_DEFAULT),
                    "id": str(uuid4()),
                    "status": "done",
                },
            }
            ws.portal.call(stub.fire, event)
            received = ws.receive_json()
            assert received["payload"]["status"] == "done"
