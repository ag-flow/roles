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
    app, stub = app_with_stub_relay
    tenant_id = uuid4()

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?tenant_id={tenant_id}") as ws:
            # Push a fake event into the queue post-connection
            event = {
                "channel": "source_items_changes",
                "payload": {
                    "table": "source_items",
                    "op": "UPDATE",
                    "tenant_id": str(tenant_id),
                    "id": str(uuid4()),
                    "status": "audio_ready",
                },
            }

            # Run fire() in the running loop via portal
            ws.portal.call(stub.fire, event)
            received = ws.receive_json()

            assert received["channel"] == "source_items_changes"
            assert received["payload"]["status"] == "audio_ready"


def test_ws_disconnect_unsubscribes(
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    app, stub = app_with_stub_relay
    tenant_id = uuid4()

    with TestClient(app) as client:
        with client.websocket_connect(f"/ws?tenant_id={tenant_id}"):
            assert stub.subscriber_count == 1

    # On context exit, the route's finally branch must unsubscribe
    assert stub.subscriber_count == 0


def test_ws_rejects_missing_tenant_id(
    app_with_stub_relay: tuple[Any, _StubRelay],
) -> None:
    app, _ = app_with_stub_relay

    with TestClient(app) as client:
        from starlette.websockets import WebSocketDisconnect

        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()
