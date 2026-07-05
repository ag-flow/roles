"""Tests for mcp_server.tools.status — roles__request_status / roles__list_requests."""

from __future__ import annotations

from typing import Any

import pytest

from role_builder.mcp_server.tools import status as tool
from role_builder.services.acquisition.errors import AcquisitionError


@pytest.fixture(autouse=True)
def _stub_db_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool.db_pool, "_pool", object(), raising=False)


async def test_request_status_forwards_request_key(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_request_status(request_key: str, *, pool: Any) -> dict[str, Any]:
        captured["request_key"] = request_key
        return {"request_key": request_key, "status": "acquiring"}

    monkeypatch.setattr(tool, "_request_status", fake_request_status)

    result = await tool.request_status("yt-x-2026-07-05")

    assert result["status"] == "acquiring"
    assert captured["request_key"] == "yt-x-2026-07-05"


async def test_request_status_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_request_status(request_key: str, *, pool: Any) -> dict[str, Any]:
        raise AcquisitionError("UNKNOWN_REQUEST", "no acquisition request 'nope'")

    monkeypatch.setattr(tool, "_request_status", fake_request_status)

    result = await tool.request_status("nope")

    assert result["error"]["code"] == "UNKNOWN_REQUEST"


async def test_list_requests_forwards_filters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_list_requests(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [{"request_key": "k"}]

    monkeypatch.setattr(tool, "_list_requests", fake_list_requests)

    result = await tool.list_requests(status="discovering", submitted_by="claude-web")

    assert result == [{"request_key": "k"}]
    assert captured["status"] == "discovering"
    assert captured["submitted_by"] == "claude-web"
