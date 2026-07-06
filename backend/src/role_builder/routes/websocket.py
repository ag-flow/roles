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

    # Lecture concurrente : `ws.receive()` capte immédiatement la fermeture du
    # client (sinon détectée seulement au prochain send, jusqu'à 30 s plus
    # tard) ; le send est protégé contre `OSError`/`ClientDisconnected`
    # (uvicorn), qui n'est PAS une WebSocketDisconnect Starlette.
    receive_task = asyncio.create_task(ws.receive())
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            done, _pending = await asyncio.wait(
                {receive_task, get_task}, timeout=30.0, return_when=asyncio.FIRST_COMPLETED
            )
            if not done:  # timeout → heartbeat (détecte une connexion half-open)
                get_task.cancel()
                await ws.send_json({"type": "ping"})
                continue
            if get_task in done:
                await ws.send_json(get_task.result())
            else:
                get_task.cancel()
            if receive_task in done:
                message = receive_task.result()  # WebSocketDisconnect si déconnecté
                if message.get("type") == "websocket.disconnect":
                    break
                receive_task = asyncio.create_task(ws.receive())  # message client ignoré
    except (WebSocketDisconnect, OSError):
        log.info(
            "ws.client_disconnected",
            tenant_id=str(user.tenant_id),
            user_id=str(user.user_id),
        )
    finally:
        receive_task.cancel()
        ws_relay.unsubscribe(queue)
