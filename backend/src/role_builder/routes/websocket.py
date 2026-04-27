"""Endpoint WebSocket : relaie les events PG NOTIFY filtrés par tenant_id.

Le client se connecte sur `/ws?tenant_id=<uuid>`. À chaque NOTIFY relayé par
`ws_relay`, un JSON `{channel, payload}` est poussé sur la WS.

Pas d'auth en MVP — sera ajouté quand le multi-tenant sera réel.
"""
from __future__ import annotations

import asyncio
from uuid import UUID

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from role_builder.services.ws_relay import ws_relay

log = structlog.get_logger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, tenant_id: UUID) -> None:
    """Accept a WS connection, subscribe to ws_relay, forward events to client."""
    await ws.accept()
    queue = ws_relay.subscribe(tenant_id=tenant_id)
    log.info("ws.client_connected", tenant_id=str(tenant_id))

    try:
        while True:
            # Wait for next event with a timeout so we can also detect client disconnect
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                # Send a heartbeat to detect a half-open connection
                await ws.send_json({"type": "ping"})
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        log.info("ws.client_disconnected", tenant_id=str(tenant_id))
    finally:
        ws_relay.unsubscribe(queue)
