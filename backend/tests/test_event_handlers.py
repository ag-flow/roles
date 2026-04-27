"""Tests for services.event_handlers — dispatch scraper events to db_helpers."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture()
def calls() -> dict[str, list[dict[str, Any]]]:
    return {
        "insert_items": [],
        "update_source_status": [],
        "update_item_status": [],
    }


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[dict[str, Any]]]) -> Any:
    """Patch the db_helpers used by event_handlers with no-op recorders."""
    from role_builder.db_helpers import source_items as si
    from role_builder.db_helpers import sources as sm

    async def fake_insert_bulk(items: list[dict[str, Any]], **kwargs: Any) -> int:
        calls["insert_items"].append({"items": items, "kwargs": kwargs})
        return len(items)

    async def fake_update_source_status(*args: Any, **kwargs: Any) -> None:
        calls["update_source_status"].append({"args": args, "kwargs": kwargs})

    async def fake_update_item_status(*args: Any, **kwargs: Any) -> None:
        calls["update_item_status"].append({"args": args, "kwargs": kwargs})

    monkeypatch.setattr(si, "insert_source_items_bulk", fake_insert_bulk)
    monkeypatch.setattr(sm, "update_source_status", fake_update_source_status)
    monkeypatch.setattr(si, "update_source_item_status", fake_update_item_status)


@pytest.fixture()
def job() -> dict[str, Any]:
    return {
        "id": uuid4(),
        "source_id": uuid4(),
        "tenant_id": uuid4(),
        "platform": "youtube",
        "command": "discover",
    }


async def test_handle_started_is_noop(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'started' / 'progress' / 'complete' events do not write to DB."""
    from role_builder.services import event_handlers

    pool = object()  # opaque, never touched (db_helpers are patched)
    await event_handlers.handle_scraper_event(
        {"type": "started", "task_id": "x"}, job, pool=pool
    )
    await event_handlers.handle_scraper_event(
        {"type": "progress", "item_id": "y", "percent": 10}, job, pool=pool
    )
    await event_handlers.handle_scraper_event(
        {"type": "complete", "downloaded": 2}, job, pool=pool
    )
    assert calls["insert_items"] == []
    assert calls["update_source_status"] == []
    assert calls["update_item_status"] == []


async def test_handle_discovered_inserts_items_and_updates_source(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'discovered' bulk-inserts items + updates source status to 'discovered'."""
    from role_builder.services import event_handlers

    pool = object()
    items = [{"id": "v1", "title": "T1"}, {"id": "v2", "title": "T2"}]
    await event_handlers.handle_scraper_event(
        {"type": "discovered", "total": 2, "items": items}, job, pool=pool
    )

    assert len(calls["insert_items"]) == 1
    inserted = calls["insert_items"][0]
    assert inserted["items"] == items
    assert inserted["kwargs"]["source_id"] == job["source_id"]
    assert inserted["kwargs"]["tenant_id"] == job["tenant_id"]

    assert len(calls["update_source_status"]) == 1
    upd = calls["update_source_status"][0]
    # update_source_status(source_id, status, *, discovered_count, ...)
    assert upd["args"][0] == job["source_id"]
    assert upd["args"][1] == "discovered"
    assert upd["kwargs"]["discovered_count"] == 2


async def test_handle_item_done_marks_audio_ready(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'item_done' updates item status to 'audio_ready' with audio_s3_key."""
    from role_builder.services import event_handlers

    pool = object()
    await event_handlers.handle_scraper_event(
        {
            "type": "item_done",
            "item_id": "vid-42",
            "audio_s3_key": "tenant/role/source/vid-42.mp3",
        },
        job,
        pool=pool,
    )
    assert len(calls["update_item_status"]) == 1
    call = calls["update_item_status"][0]
    # update_source_item_status(source_id, platform_item_id, status, *, audio_s3_key, ...)
    assert call["args"][0] == job["source_id"]
    assert call["args"][1] == "vid-42"
    assert call["args"][2] == "audio_ready"
    assert call["kwargs"]["audio_s3_key"] == "tenant/role/source/vid-42.mp3"


async def test_handle_item_failed_marks_failed_with_error(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'item_failed' updates item status to 'failed' with error message."""
    from role_builder.services import event_handlers

    pool = object()
    await event_handlers.handle_scraper_event(
        {"type": "item_failed", "item_id": "vid-9", "error": "geo-restricted"},
        job,
        pool=pool,
    )
    assert len(calls["update_item_status"]) == 1
    call = calls["update_item_status"][0]
    assert call["args"][0] == job["source_id"]
    assert call["args"][1] == "vid-9"
    assert call["args"][2] == "failed"
    assert call["kwargs"]["error"] == "geo-restricted"


async def test_handle_unknown_and_internal_events_are_noop_safe(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'_invalid_line' / '_exit' / 'error' / unknown types log but do not raise."""
    from role_builder.services import event_handlers

    pool = object()
    for ev in (
        {"type": "_invalid_line", "raw": "garbage"},
        {"type": "_exit", "returncode": 0},
        {"type": "error", "message": "boom"},
        {"type": "wat"},
    ):
        await event_handlers.handle_scraper_event(ev, job, pool=pool)
    assert calls["insert_items"] == []
    assert calls["update_source_status"] == []
    assert calls["update_item_status"] == []
