"""Endpoint WebSocket : relaie les events PG NOTIFY filtrés par tenant_id.

Le client se connecte sur ``/ws?token=<access_token>``. Le tenant_id est
déduit du JWT (claim ``sub``) — pas accepté en query param pour empêcher
le tenant spoofing. À chaque NOTIFY relayé par ``ws_relay``, un JSON
``{channel, payload}`` est poussé sur la WS.

Si ``settings.disable_auth=True``, l'auth est bypass et tenant_id =
TENANT_ID_DEFAULT (mode dev/tests).
"""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from role_builder.auth.dependencies import authenticate_websocket
from role_builder.auth.keycloak import InvalidTokenError
from role_builder.services.ws_relay import ws_relay

log = structlog.get_logger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(
    ws: WebSocket,
    token: str | None = None,
) -> None:
    """Accept WS, valide le token, subscribe ws_relay, forward events."""
    try:
        user = await authenticate_websocket(token)
    except InvalidTokenError as exc:
        log.warning("ws.auth_failed", reason=str(exc))
        # 4401 (custom code dans l'espace 4xxx réservé app) — close code 1008
        # est aussi acceptable. On utilise 1008 (Policy Violation) standard.
        await ws.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return

    await ws.accept()
    queue = ws_relay.subscribe(tenant_id=user.tenant_id)
    log.info(
        "ws.client_connected",
        tenant_id=str(user.tenant_id),
        user_id=str(user.user_id),
    )

    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
            except TimeoutError:
                # Heartbeat pour détecter une connexion half-open
                await ws.send_json({"type": "ping"})
                continue
            await ws.send_json(event)
    except WebSocketDisconnect:
        log.info(
            "ws.client_disconnected",
            tenant_id=str(user.tenant_id),
            user_id=str(user.user_id),
        )
    finally:
        ws_relay.unsubscribe(queue)
