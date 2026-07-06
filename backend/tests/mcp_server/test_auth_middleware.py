"""Tests du middleware d'auth de la façade MCP (BUG-34)."""

from __future__ import annotations

from typing import Any

import pytest

from role_builder.mcp_server.auth_middleware import MCPAuthMiddleware

pytestmark = pytest.mark.asyncio


class _AppSpy:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


async def _drive(mw: MCPAuthMiddleware, scope: dict[str, Any]) -> int | None:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await mw(scope, receive, send)
    starts = [m for m in sent if m["type"] == "http.response.start"]
    return starts[0]["status"] if starts else None


def _http_scope(auth: str | None = None) -> dict[str, Any]:
    headers = [(b"authorization", auth.encode())] if auth is not None else []
    return {"type": "http", "headers": headers}


async def test_passthrough_when_no_token() -> None:
    """Token vide (dev/test) : le mount est ouvert, l'app est appelée."""
    app = _AppSpy()
    mw = MCPAuthMiddleware(app, token="")
    assert await _drive(mw, _http_scope()) == 200
    assert app.called is True


async def test_rejects_missing_or_wrong_token() -> None:
    app = _AppSpy()
    mw = MCPAuthMiddleware(app, token="s3cret")
    assert await _drive(mw, _http_scope()) == 401
    assert await _drive(mw, _http_scope("Bearer nope")) == 401
    assert app.called is False


async def test_accepts_valid_token() -> None:
    app = _AppSpy()
    mw = MCPAuthMiddleware(app, token="s3cret")
    assert await _drive(mw, _http_scope("Bearer s3cret")) == 200
    assert app.called is True


async def test_non_http_scope_passes_through() -> None:
    """Les scopes lifespan/websocket ne sont jamais bloqués."""
    app = _AppSpy()
    mw = MCPAuthMiddleware(app, token="s3cret")
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "lifespan.startup"}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    await mw({"type": "lifespan"}, receive, send)
    assert app.called is True
