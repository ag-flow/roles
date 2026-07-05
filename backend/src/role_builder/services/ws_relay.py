"""Pont entre les channels PG NOTIFY et les clients WebSocket.

Maintient une connexion asyncpg dédiée et relaie chaque NOTIFY reçu vers les
queues asyncio des subscribers (filtrées par `tenant_id`).

Channels écoutés (cf. migration 0010) :
- source_items_changes
- workers_changes
- keys_changes

Le payload émis par la fonction PG `notify_event` est un JSON :
    {"table": ..., "op": ..., "tenant_id": ..., "id": ..., "status": ...}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.config import settings

log = structlog.get_logger(__name__)

_CHANNELS = (
    "source_items_changes",
    "workers_changes",
    "keys_changes",
)


class WSRelay:
    """Singleton-style relay between PG NOTIFY and WebSocket subscribers.

    Owns a dedicated asyncpg connection (NOT pooled — listeners are
    per-connection in Postgres) and a list of subscriber queues tagged by
    tenant_id.
    """

    def __init__(self, *, dsn: str) -> None:
        self._dsn = dsn
        self._conn: asyncpg.Connection | None = None
        # Each entry : (tenant_id, queue)
        self._subscribers: list[tuple[UUID, asyncio.Queue[dict[str, Any]]]] = []

    async def start(self) -> None:
        """Open the dedicated connection and register listeners on the 3 channels."""
        self._conn = await asyncpg.connect(self._dsn)
        for channel in _CHANNELS:
            await self._conn.add_listener(channel, self._on_notify)
        log.info("ws_relay.started", channels=list(_CHANNELS))

    async def stop(self) -> None:
        """Close the connection (listeners are dropped automatically)."""
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None
                self._subscribers.clear()
        log.info("ws_relay.stopped")

    def subscribe(self, *, tenant_id: UUID) -> asyncio.Queue[dict[str, Any]]:
        """Register a subscriber queue for `tenant_id`. Caller MUST unsubscribe later."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.append((tenant_id, queue))
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        """Remove a subscriber queue. Idempotent."""
        self._subscribers = [(t, q) for (t, q) in self._subscribers if q is not queue]

    # --- internals -------------------------------------------------------

    def _on_notify(
        self,
        connection: asyncpg.Connection,  # noqa: ARG002 — required by asyncpg signature
        pid: int,  # noqa: ARG002
        channel: str,
        payload: str,
    ) -> None:
        """asyncpg listener callback. Decode payload, dispatch to matching queues."""
        try:
            decoded = json.loads(payload)
        except (TypeError, ValueError):
            log.warning("ws_relay.invalid_payload", channel=channel, payload=payload)
            return

        event = {"channel": channel, "payload": decoded}
        target_tenant = decoded.get("tenant_id")
        if target_tenant is None:
            return

        for tenant_id, queue in self._subscribers:
            if str(tenant_id) == str(target_tenant):
                # put_nowait: dropping events on a slow client is acceptable here
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:  # pragma: no cover — unbounded by default
                    log.warning("ws_relay.queue_full", channel=channel)


# Singleton consumed by routes/websocket and lifespan
ws_relay = WSRelay(dsn=settings.database_url)
