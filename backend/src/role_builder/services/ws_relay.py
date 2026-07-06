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

    def __init__(self, *, dsn: str, health_interval_s: float = 5.0) -> None:
        self._dsn = dsn
        self._health_interval_s = health_interval_s
        self._conn: asyncpg.Connection | None = None
        # Each entry : (tenant_id, queue)
        self._subscribers: list[tuple[UUID, asyncio.Queue[dict[str, Any]]]] = []
        self._stop = asyncio.Event()
        self._monitor_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Ouvre la connexion, enregistre les listeners, lance le moniteur.

        La connexion LISTEN dédiée n'est pas reconnectée par asyncpg : si elle
        tombe (restart PG, coupure, idle timeout d'un proxy), les NOTIFY ne
        seraient plus jamais relayés. Un moniteur de fond détecte la coupure
        et reconnecte avec ré-enregistrement des listeners.
        """
        self._stop.clear()
        await self._connect()
        self._monitor_task = asyncio.create_task(self._monitor(), name="ws-relay-monitor")
        log.info("ws_relay.started", channels=list(_CHANNELS))

    async def stop(self) -> None:
        """Arrête le moniteur et ferme la connexion (listeners dropés automatiquement)."""
        self._stop.set()
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 — arrêt best-effort
                pass
            self._monitor_task = None
        if self._conn is not None:
            try:
                await self._conn.close()
            finally:
                self._conn = None
                self._subscribers.clear()
        log.info("ws_relay.stopped")

    async def _connect(self) -> None:
        """(Re)ouvre la connexion dédiée et enregistre les 3 listeners."""
        conn = await asyncpg.connect(self._dsn)
        for channel in _CHANNELS:
            await conn.add_listener(channel, self._on_notify)
        self._conn = conn

    async def _monitor(self) -> None:
        """Surveille la connexion LISTEN et reconnecte à la moindre coupure."""
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self._health_interval_s)
                return  # stop demandé
            except TimeoutError:
                pass
            if self._conn is None or self._is_closed(self._conn):
                log.warning("ws_relay.connection_lost_reconnecting")
                try:
                    await self._connect()
                    log.info("ws_relay.reconnected")
                except Exception:  # noqa: BLE001 — on retente au prochain tick
                    log.exception("ws_relay.reconnect_failed")

    @staticmethod
    def _is_closed(conn: asyncpg.Connection) -> bool:
        """True si la connexion asyncpg est fermée (tolère les doubles de test)."""
        is_closed = getattr(conn, "is_closed", None)
        return bool(is_closed()) if callable(is_closed) else False

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
