"""Tests for services.ws_relay — pont entre PG NOTIFY et clients WebSocket."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID, uuid4

import pytest


class _StubAsyncpgConn:
    """Stub asyncpg connection capturing add_listener / remove_listener calls."""

    def __init__(self) -> None:
        self.listeners: dict[str, list[Any]] = {}
        self.closed = False

    async def add_listener(self, channel: str, callback: Any) -> None:
        self.listeners.setdefault(channel, []).append(callback)

    async def remove_listener(self, channel: str, callback: Any) -> None:
        self.listeners[channel].remove(callback)

    async def close(self) -> None:
        self.closed = True

    def fire(self, channel: str, payload: str) -> None:
        """Test helper: simulate a NOTIFY arrival, calling each listener with asyncpg signature."""
        for cb in self.listeners.get(channel, []):
            cb(self, 0, channel, payload)


@pytest.fixture()
def stub_conn(monkeypatch: pytest.MonkeyPatch) -> _StubAsyncpgConn:
    """Patch asyncpg.connect to return a stub connection."""
    import role_builder.services.ws_relay as ws_relay_module

    conn = _StubAsyncpgConn()

    async def fake_connect(dsn: str) -> _StubAsyncpgConn:  # noqa: ARG001
        return conn

    monkeypatch.setattr(ws_relay_module.asyncpg, "connect", fake_connect)
    return conn


def _make_payload(
    *, tenant_id: UUID, table: str = "source_items", status: str = "audio_ready"
) -> str:
    return json.dumps(
        {
            "table": table,
            "op": "UPDATE",
            "tenant_id": str(tenant_id),
            "id": str(uuid4()),
            "status": status,
        }
    )


async def test_start_listens_on_4_channels(stub_conn: _StubAsyncpgConn) -> None:
    from role_builder.services.ws_relay import WSRelay

    relay = WSRelay(dsn="postgresql://stub")
    await relay.start()

    assert set(stub_conn.listeners.keys()) == {
        "source_items_changes",
        "runs_changes",
        "workers_changes",
        "keys_changes",
    }
    for chan in stub_conn.listeners.values():
        assert len(chan) == 1

    await relay.stop()
    assert stub_conn.closed is True


async def test_subscribe_receives_event_for_matching_tenant(stub_conn: _StubAsyncpgConn) -> None:
    from role_builder.services.ws_relay import WSRelay

    tenant_id = uuid4()
    relay = WSRelay(dsn="postgresql://stub")
    await relay.start()

    queue = relay.subscribe(tenant_id=tenant_id)
    payload = _make_payload(tenant_id=tenant_id)
    stub_conn.fire("source_items_changes", payload)

    event = await asyncio.wait_for(queue.get(), timeout=0.5)
    assert event["channel"] == "source_items_changes"
    assert event["payload"]["tenant_id"] == str(tenant_id)
    assert event["payload"]["status"] == "audio_ready"

    await relay.stop()


async def test_subscribe_filters_out_other_tenants(stub_conn: _StubAsyncpgConn) -> None:
    from role_builder.services.ws_relay import WSRelay

    my_tenant = uuid4()
    other_tenant = uuid4()
    relay = WSRelay(dsn="postgresql://stub")
    await relay.start()

    queue = relay.subscribe(tenant_id=my_tenant)
    stub_conn.fire("runs_changes", _make_payload(tenant_id=other_tenant, table="runs"))

    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)

    # And events for the right tenant still go through
    stub_conn.fire("runs_changes", _make_payload(tenant_id=my_tenant, table="runs"))
    event = await asyncio.wait_for(queue.get(), timeout=0.5)
    assert event["payload"]["tenant_id"] == str(my_tenant)

    await relay.stop()


async def test_unsubscribe_stops_delivery(stub_conn: _StubAsyncpgConn) -> None:
    from role_builder.services.ws_relay import WSRelay

    tenant_id = uuid4()
    relay = WSRelay(dsn="postgresql://stub")
    await relay.start()

    queue = relay.subscribe(tenant_id=tenant_id)
    relay.unsubscribe(queue)

    stub_conn.fire("source_items_changes", _make_payload(tenant_id=tenant_id))
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(queue.get(), timeout=0.1)

    await relay.stop()
