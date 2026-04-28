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
def calls_with_jobs() -> dict[str, list[dict[str, Any]]]:
    """Extended call recorder including transcription_jobs.insert_job."""
    return {
        "insert_items": [],
        "update_source_status": [],
        "update_item_status": [],
        "insert_transcription_job": [],
        "get_primary_key": [],
        "get_source": [],
        "get_user_id_for_project": [],
        "get_by_platform_id": [],
    }


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[dict[str, Any]]]) -> Any:
    """Patch the db_helpers used by event_handlers with no-op recorders."""
    from role_builder.db_helpers import role_projects as rp
    from role_builder.db_helpers import source_items as si
    from role_builder.db_helpers import sources as sm
    from role_builder.db_helpers import transcription_jobs as tj
    from role_builder.db_helpers import transcription_keys as tk

    async def fake_insert_bulk(items: list[dict[str, Any]], **kwargs: Any) -> int:
        calls["insert_items"].append({"items": items, "kwargs": kwargs})
        return len(items)

    async def fake_update_source_status(*args: Any, **kwargs: Any) -> None:
        calls["update_source_status"].append({"args": args, "kwargs": kwargs})

    async def fake_update_item_status(*args: Any, **kwargs: Any) -> None:
        calls["update_item_status"].append({"args": args, "kwargs": kwargs})

    # Defaults for the item_done path : pas de primary key, source vide
    async def fake_get_source(_: Any, *, pool: Any) -> dict[str, Any]:
        return {"role_project_id": uuid4()}

    async def fake_get_user_id(_: Any, *, pool: Any) -> Any:
        return uuid4()

    async def fake_get_primary(_: Any, *, pool: Any) -> dict[str, Any] | None:
        return None  # par défaut : pas de primary key → shared_default

    async def fake_get_by_platform_id(
        _source_id: Any, _platform_item_id: str, *, pool: Any
    ) -> dict[str, Any]:
        return {"id": uuid4(), "tenant_id": uuid4()}

    async def fake_insert_job(**kwargs: Any) -> Any:
        return uuid4()

    monkeypatch.setattr(si, "insert_source_items_bulk", fake_insert_bulk)
    monkeypatch.setattr(sm, "update_source_status", fake_update_source_status)
    monkeypatch.setattr(si, "update_source_item_status", fake_update_item_status)
    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(rp, "get_user_id_for_project", fake_get_user_id)
    monkeypatch.setattr(tk, "get_primary_key", fake_get_primary)
    monkeypatch.setattr(si, "get_by_platform_id", fake_get_by_platform_id)
    monkeypatch.setattr(tj, "insert_job", fake_insert_job)


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
    await event_handlers.handle_scraper_event({"type": "started", "task_id": "x"}, job, pool=pool)
    await event_handlers.handle_scraper_event(
        {"type": "progress", "item_id": "y", "percent": 10}, job, pool=pool
    )
    await event_handlers.handle_scraper_event({"type": "complete", "downloaded": 2}, job, pool=pool)
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


async def test_handle_item_done_marks_queued_transcription(
    patched: Any, job: dict[str, Any], calls: dict[str, list[dict[str, Any]]]
) -> None:
    """'item_done' marque source_item 'queued_transcription' (avec audio_s3_key)."""
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
    assert call["args"][2] == "queued_transcription"
    assert call["kwargs"]["audio_s3_key"] == "tenant/role/source/vid-42.mp3"


async def test_handle_item_done_creates_transcription_job_with_user_pool(
    monkeypatch: pytest.MonkeyPatch, job: dict[str, Any]
) -> None:
    """Avec une primary key active, transcription_jobs.insert_job est appelé
    avec worker_pool_id='user_<user_id>'."""
    from role_builder.db_helpers import role_projects as rp
    from role_builder.db_helpers import source_items as si
    from role_builder.db_helpers import sources as sm
    from role_builder.db_helpers import transcription_jobs as tj
    from role_builder.db_helpers import transcription_keys as tk
    from role_builder.services import event_handlers

    role_project_id = uuid4()
    user_id = uuid4()
    item_uuid = uuid4()
    primary_key = {
        "id": uuid4(),
        "user_id": user_id,
        "provider": "openai-whisper",
        "status": "active",
        "is_primary": True,
    }
    captured_insert: dict[str, Any] = {}

    async def fake_get_source(_: Any, *, pool: Any) -> dict[str, Any]:
        return {"role_project_id": role_project_id}

    async def fake_get_user_id(rp_id: Any, *, pool: Any) -> Any:
        assert rp_id == role_project_id
        return user_id

    async def fake_get_primary(uid: Any, *, pool: Any) -> dict[str, Any]:
        assert uid == user_id
        return primary_key

    async def fake_get_by_platform_id(
        _source_id: Any, _platform_item_id: str, *, pool: Any
    ) -> dict[str, Any]:
        return {"id": item_uuid, "tenant_id": job["tenant_id"]}

    async def fake_insert_job(**kwargs: Any) -> Any:
        captured_insert.update(kwargs)
        return uuid4()

    async def fake_update_item_status(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(rp, "get_user_id_for_project", fake_get_user_id)
    monkeypatch.setattr(tk, "get_primary_key", fake_get_primary)
    monkeypatch.setattr(si, "get_by_platform_id", fake_get_by_platform_id)
    monkeypatch.setattr(tj, "insert_job", fake_insert_job)
    monkeypatch.setattr(si, "update_source_item_status", fake_update_item_status)

    pool = object()
    await event_handlers.handle_scraper_event(
        {
            "type": "item_done",
            "item_id": "vid-1",
            "audio_s3_key": "tenant/role/src/vid-1.mp3",
        },
        job,
        pool=pool,
    )

    assert captured_insert["worker_pool_id"] == f"user_{user_id}"
    assert captured_insert["source_item_id"] == item_uuid
    assert captured_insert["audio_s3_key"] == "tenant/role/src/vid-1.mp3"
    assert captured_insert["tenant_id"] == job["tenant_id"]


async def test_handle_item_done_creates_transcription_job_shared_default_when_no_key(
    monkeypatch: pytest.MonkeyPatch, job: dict[str, Any]
) -> None:
    """Sans primary key active, worker_pool_id='shared_default'."""
    from role_builder.db_helpers import role_projects as rp
    from role_builder.db_helpers import source_items as si
    from role_builder.db_helpers import sources as sm
    from role_builder.db_helpers import transcription_jobs as tj
    from role_builder.db_helpers import transcription_keys as tk
    from role_builder.services import event_handlers

    user_id = uuid4()
    captured_insert: dict[str, Any] = {}

    async def fake_get_source(_: Any, *, pool: Any) -> dict[str, Any]:
        return {"role_project_id": uuid4()}

    async def fake_get_user_id(_: Any, *, pool: Any) -> Any:
        return user_id

    async def fake_get_primary(_: Any, *, pool: Any) -> None:
        return None

    async def fake_get_by_platform_id(
        _source_id: Any, _platform_item_id: str, *, pool: Any
    ) -> dict[str, Any]:
        return {"id": uuid4(), "tenant_id": job["tenant_id"]}

    async def fake_insert_job(**kwargs: Any) -> Any:
        captured_insert.update(kwargs)
        return uuid4()

    async def fake_update_item_status(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(rp, "get_user_id_for_project", fake_get_user_id)
    monkeypatch.setattr(tk, "get_primary_key", fake_get_primary)
    monkeypatch.setattr(si, "get_by_platform_id", fake_get_by_platform_id)
    monkeypatch.setattr(tj, "insert_job", fake_insert_job)
    monkeypatch.setattr(si, "update_source_item_status", fake_update_item_status)

    pool = object()
    await event_handlers.handle_scraper_event(
        {
            "type": "item_done",
            "item_id": "vid-2",
            "audio_s3_key": "tenant/role/src/vid-2.mp3",
        },
        job,
        pool=pool,
    )

    assert captured_insert["worker_pool_id"] == "shared_default"


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
