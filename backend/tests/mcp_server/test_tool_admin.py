"""Tests for mcp_server.tools.admin — roles__cancel_request / roles__retry_failed."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest

from role_builder.mcp_server.tools import admin as tool
from role_builder.services.acquisition.errors import AcquisitionError


@pytest.fixture(autouse=True)
def _stub_db_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tool.db_pool, "_pool", object(), raising=False)


async def test_cancel_request_forwards_note(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_cancel(request_key: str, note: str | None, *, pool: Any) -> dict[str, int]:
        captured["request_key"] = request_key
        captured["note"] = note
        return {"cancelled_jobs": 2, "deposited_kept": 1}

    monkeypatch.setattr(tool, "_cancel_request", fake_cancel)

    result = await tool.cancel_request("yt-x-2026-07-05", note="plus besoin")

    assert result == {"cancelled_jobs": 2, "deposited_kept": 1}
    assert captured["note"] == "plus besoin"


async def test_cancel_request_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_cancel(request_key: str, note: str | None, *, pool: Any) -> dict[str, int]:
        raise AcquisitionError("ALREADY_CANCELLED", f"{request_key!r} is already cancelled")

    monkeypatch.setattr(tool, "_cancel_request", fake_cancel)

    result = await tool.cancel_request("yt-x-2026-07-05")

    assert result["error"]["code"] == "ALREADY_CANCELLED"


async def test_retry_failed_converts_item_ids_to_uuid(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    item_id = uuid4()

    async def fake_retry(request_key: str, item_ids: Any, *, pool: Any) -> dict[str, int]:
        captured["item_ids"] = item_ids
        return {"retried_count": 1}

    monkeypatch.setattr(tool, "_retry_failed", fake_retry)

    result = await tool.retry_failed("yt-x-2026-07-05", item_ids=[str(item_id)])

    assert result == {"retried_count": 1}
    assert captured["item_ids"] == [item_id]
    assert isinstance(captured["item_ids"][0], UUID)


async def test_retry_failed_without_item_ids_retries_all(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_retry(request_key: str, item_ids: Any, *, pool: Any) -> dict[str, int]:
        captured["item_ids"] = item_ids
        return {"retried_count": 3}

    monkeypatch.setattr(tool, "_retry_failed", fake_retry)

    await tool.retry_failed("yt-x-2026-07-05")

    assert captured["item_ids"] is None


async def test_retry_failed_returns_uniform_error_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_retry(request_key: str, item_ids: Any, *, pool: Any) -> dict[str, int]:
        raise AcquisitionError("UNKNOWN_REQUEST", "no acquisition request 'nope'")

    monkeypatch.setattr(tool, "_retry_failed", fake_retry)

    result = await tool.retry_failed("nope")

    assert result["error"]["code"] == "UNKNOWN_REQUEST"
