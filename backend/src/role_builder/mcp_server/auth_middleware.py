"""Middleware ASGI d'authentification de la façade MCP `roles__*` (BUG-34).

Le mount `/mcp` expose des tools sensibles (submit_acquisition, slots d'upload
MinIO présignés, cancel_request…) : contrairement à l'API REST, il n'a aucune
dépendance d'auth. Ce middleware exige un jeton machine (Bearer) partagé avec
la passerelle. Désactivé si `token` est vide (dev/test) — pass-through.

Le protocole streamable-http rend malaisée l'injection d'une dépendance
FastAPI classique ; un middleware ASGI sur le mount est la voie simple. Les
scopes non-http (lifespan, websocket) sont transmis tels quels.
"""

from __future__ import annotations

import hmac
from collections.abc import Awaitable, Callable
from typing import Any

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]


class MCPAuthMiddleware:
    """Vérifie un Bearer machine sur les requêtes HTTP du mount MCP."""

    def __init__(self, app: Callable[..., Awaitable[None]], *, token: str) -> None:
        self._app = app
        self._expected = f"Bearer {token}" if token else ""

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._expected:
            await self._app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"authorization", b"").decode("latin-1")
        if not hmac.compare_digest(provided, self._expected):
            await self._send_401(send)
            return
        await self._app(scope, receive, send)

    @staticmethod
    async def _send_401(send: Send) -> None:
        await send({
            "type": "http.response.start",
            "status": 401,
            "headers": [(b"content-type", b"application/json"),
                        (b"www-authenticate", b"Bearer")],
        })
        await send({"type": "http.response.body", "body": b'{"error":"unauthorized"}'})
