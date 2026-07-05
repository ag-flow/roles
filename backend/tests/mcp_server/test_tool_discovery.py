"""Tests for mcp_server.tools.discovery — roles__list_discovered / roles__select_items."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.mcp_server.tools import discovery as tool
from role_builder.services.acquisition.errors import AcquisitionError


@pytest.fixture(autouse=True)
def _stub_db_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool.db_pool, "_pool", object(), raising=False)


async def test_list_discovered_forwards_cursor_and_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_list_discovered(**kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {"request_key": "k", "discovery_complete": True, "items": [], "next_cursor": None}

    monkeypatch.setattr(tool, "_list_discovered", fake_list_discovered)

    result = await tool.list_discovered("yt-x-2026-07-05", cursor="10", limit=25)

    assert result["discovery_complete"] is True
    assert captured["request_key"] == "yt-x-2026-07-05"
    assert captured["cursor"] == "10"
    assert captured["limit"] == 25


async def test_list_discovered_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_list_discovered(**kwargs: Any) -> dict[str, Any]:
        raise AcquisitionError("UNKNOWN_REQUEST", "no acquisition request 'nope'")

    monkeypatch.setattr(tool, "_list_discovered", fake_list_discovered)

    result = await tool.list_discovered("nope")

    assert result["error"]["code"] == "UNKNOWN_REQUEST"


async def test_select_items_converts_string_item_ids_to_uuid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    item_id = uuid4()

    async def fake_select_items(**kwargs: Any) -> dict[str, int]:
        captured.update(kwargs)
        return {"selected_count": 1, "queued_count": 1}

    monkeypatch.setattr(tool, "_select_items", fake_select_items)

    result = await tool.select_items("yt-x-2026-07-05", item_ids=[str(item_id)])

    assert result == {"selected_count": 1, "queued_count": 1}
    assert captured["item_ids"] == [item_id]
    assert isinstance(captured["item_ids"][0], UUID)
    assert captured["filters"] is None


async def test_select_items_forwards_filters_when_no_item_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_select_items(**kwargs: Any) -> dict[str, int]:
        captured.update(kwargs)
        return {"selected_count": 3, "queued_count": 3}

    monkeypatch.setattr(tool, "_select_items", fake_select_items)

    await tool.select_items("yt-x-2026-07-05", filters={"min_duration_s": 60})

    assert captured["item_ids"] is None
    assert captured["filters"] == {"min_duration_s": 60}


async def test_select_items_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_select_items(**kwargs: Any) -> dict[str, int]:
        raise AcquisitionError("UNKNOWN_REQUEST", "no acquisition request 'nope'")

    monkeypatch.setattr(tool, "_select_items", fake_select_items)

    result = await tool.select_items("nope", item_ids=[])

    assert result["error"]["code"] == "UNKNOWN_REQUEST"
