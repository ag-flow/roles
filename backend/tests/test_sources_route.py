"""Tests for routes.sources — REST endpoints sources + items + select."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

# user_id du stub disable_auth (_disabled_user) — propriétaire attendu.
_OWNER_ID = UUID("00000000-0000-0000-0000-000000000001")


def _now_iso() -> datetime:
    return datetime.now(tz=UTC)


def _patch_owner(
    monkeypatch: pytest.MonkeyPatch, owner_id: UUID = _OWNER_ID
) -> None:
    """Stub role_projects.get_user_id_for_project → owner_id (ownership check)."""
    from role_builder.db_helpers import role_projects as rp_helper
    from role_builder.routes import sources as sources_route

    async def fake_owner(role_project_id: UUID, *, pool: Any) -> UUID:  # noqa: ARG001
        return owner_id

    monkeypatch.setattr(sources_route.role_projects_helper, "get_user_id_for_project", fake_owner)
    monkeypatch.setattr(rp_helper, "get_user_id_for_project", fake_owner)


def _source_row(*, source_id: UUID, role_project_id: UUID) -> dict[str, Any]:
    return {
        "id": source_id,
        "role_project_id": role_project_id,
        "tenant_id": uuid4(),
        "platform": "youtube",
        "source_type": "channel",
        "url": "https://www.youtube.com/@example",
        "status": "pending_discovery",
        "discovered_count": None,
        "error": None,
        "credentials_id": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


def test_post_create_source_returns_201_and_body(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/role-projects/{rpid}/sources : insert + return SourceResponse."""
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    role_project_id = uuid4()
    new_source_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_insert(**kwargs: Any) -> UUID:
        captured.update(kwargs)
        return new_source_id

    async def fake_get(source_id: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=source_id, role_project_id=role_project_id)

    monkeypatch.setattr(sources_route.sources_helper, "insert_source", fake_insert)
    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get)
    # also patch the original module so other imports stay consistent
    monkeypatch.setattr(sources_helper, "insert_source", fake_insert)
    monkeypatch.setattr(sources_helper, "get_source", fake_get)
    _patch_owner(monkeypatch)  # projet appartenant à l'appelant

    body = {
        "url": "https://www.youtube.com/@example",
        "platform": "youtube",
        "source_type": "channel",
    }
    resp = client.post(f"/api/role-projects/{role_project_id}/sources", json=body)

    assert resp.status_code == 201, resp.text
    payload = resp.json()
    assert payload["id"] == str(new_source_id)
    assert payload["platform"] == "youtube"
    assert payload["source_type"] == "channel"
    assert captured["role_project_id"] == role_project_id
    assert captured["platform"] == "youtube"
    assert captured["source_type"] == "channel"


def test_post_create_source_422_on_invalid_body(client: TestClient) -> None:
    """POST without url field → 422 from Pydantic validation."""
    role_project_id = uuid4()
    resp = client.post(
        f"/api/role-projects/{role_project_id}/sources",
        json={"platform": "youtube", "source_type": "channel"},
    )
    assert resp.status_code == 422


def test_post_discover_creates_job_and_returns_202(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST /api/sources/{id}/discover : insert scraping_job command='discover'."""
    from role_builder.db_helpers import scraping_jobs as jobs_helper
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    source_id = uuid4()
    job_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_get(sid: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=sid, role_project_id=uuid4())

    async def fake_insert_job(**kwargs: Any) -> UUID:
        captured.update(kwargs)
        return job_id

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get)
    monkeypatch.setattr(sources_route.jobs_helper, "insert_job", fake_insert_job)
    monkeypatch.setattr(sources_helper, "get_source", fake_get)
    monkeypatch.setattr(jobs_helper, "insert_job", fake_insert_job)
    _patch_owner(monkeypatch)

    resp = client.post(f"/api/sources/{source_id}/discover")
    assert resp.status_code == 202, resp.text
    assert resp.json() == {"job_id": str(job_id)}

    assert captured["source_id"] == source_id
    assert captured["command"] == "discover"


def test_post_discover_404_on_unknown_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    async def fake_get(sid: UUID, *, pool: Any) -> None:  # noqa: ARG001
        return None

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get)
    monkeypatch.setattr(sources_helper, "get_source", fake_get)

    resp = client.post(f"/api/sources/{uuid4()}/discover")
    assert resp.status_code == 404


def test_get_items_applies_filters_and_pagination(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /api/sources/{id}/items forwards filters to list_items_by_source."""
    from role_builder.db_helpers import source_items as items_helper
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    source_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_get_source(sid: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=sid, role_project_id=uuid4())

    async def fake_list(sid: UUID, **kwargs: Any) -> list[dict[str, Any]]:
        captured["source_id"] = sid
        captured.update(kwargs)
        return [
            {
                "id": uuid4(),
                "platform_item_id": "abc123",
                "title": "Vidéo de test",
                "duration_s": 120,
                "published_at": _now_iso(),
                "thumbnail_url": "https://example/thumb.jpg",
                "status": "pending_download",
                "selected": False,
                "audio_s3_key": None,
                "error": None,
            }
        ]

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(sources_route.items_helper, "list_items_by_source", fake_list)
    monkeypatch.setattr(items_helper, "list_items_by_source", fake_list)
    _patch_owner(monkeypatch)

    resp = client.get(
        f"/api/sources/{source_id}/items",
        params={"min_duration_s": 60, "status": "pending_download", "limit": 25, "offset": 0},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["platform_item_id"] == "abc123"

    assert captured["source_id"] == source_id
    assert captured["min_duration_s"] == 60
    assert captured["status"] == "pending_download"
    assert captured["limit"] == 25
    assert captured["offset"] == 0


def test_post_select_items_marks_selected_and_creates_jobs(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """POST select/items : update selected=true + insert un job download par item."""
    from role_builder.db_helpers import scraping_jobs as jobs_helper
    from role_builder.db_helpers import source_items as items_helper
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    source_id = uuid4()
    item_id_1 = uuid4()
    item_id_2 = uuid4()

    captured: dict[str, Any] = {"select": [], "jobs": []}

    async def fake_get_source(sid: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=sid, role_project_id=uuid4())

    async def fake_list_by_ids(sid: UUID, ids: list[UUID], *, pool: Any) -> list[dict[str, Any]]:  # noqa: ARG001
        return [{"id": i, "platform_item_id": f"p-{i}"} for i in ids if i in {item_id_1, item_id_2}]

    async def fake_active_job(item_id: UUID, command: str, *, pool: Any) -> bool:  # noqa: ARG001
        return False  # aucun download en vol

    async def fake_select(sid: UUID, item_ids: list[UUID], **kwargs: Any) -> int:
        captured["select"].append((sid, item_ids, kwargs))
        return len(item_ids)

    async def fake_insert_job(**kwargs: Any) -> UUID:
        captured["jobs"].append(kwargs)
        return uuid4()

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(sources_route.items_helper, "select_items", fake_select)
    monkeypatch.setattr(sources_route.items_helper, "list_items_by_ids", fake_list_by_ids)
    monkeypatch.setattr(sources_route.jobs_helper, "insert_job", fake_insert_job)
    monkeypatch.setattr(sources_route.jobs_helper, "get_active_job_for_item", fake_active_job)
    monkeypatch.setattr(sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(items_helper, "select_items", fake_select)
    monkeypatch.setattr(items_helper, "list_items_by_ids", fake_list_by_ids)
    monkeypatch.setattr(jobs_helper, "insert_job", fake_insert_job)
    monkeypatch.setattr(jobs_helper, "get_active_job_for_item", fake_active_job)
    _patch_owner(monkeypatch)

    resp = client.post(
        f"/api/sources/{source_id}/items/select",
        json={"item_ids": [str(item_id_1), str(item_id_2)], "deselect_others": True},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["selected_count"] == 2
    assert body["jobs_created"] == 2

    # select_items called once with deselect_others=True
    assert len(captured["select"]) == 1
    sid_used, ids_used, kw = captured["select"][0]
    assert sid_used == source_id
    assert set(ids_used) == {item_id_1, item_id_2}
    assert kw.get("deselect_others") is True

    # one job per item, all command='download'
    assert len(captured["jobs"]) == 2
    for job_kwargs in captured["jobs"]:
        assert job_kwargs["command"] == "download"
        assert job_kwargs["source_id"] == source_id
        assert job_kwargs["source_item_id"] in {item_id_1, item_id_2}


def test_items_of_another_users_source_are_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Source d'un role_project appartenant à un autre user → 404 (BUG-33)."""
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    async def fake_get_source(sid: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=sid, role_project_id=uuid4())

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(sources_helper, "get_source", fake_get_source)
    _patch_owner(monkeypatch, owner_id=uuid4())  # propriétaire ≠ appelant

    resp = client.get(f"/api/sources/{uuid4()}/items")
    assert resp.status_code == 404


def test_select_unknown_item_is_400(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """item_id hors de la source → 400, aucune écriture (BUG-32)."""
    from role_builder.db_helpers import scraping_jobs as jobs_helper
    from role_builder.db_helpers import source_items as items_helper
    from role_builder.db_helpers import sources as sources_helper
    from role_builder.routes import sources as sources_route

    source_id = uuid4()
    good_id = uuid4()
    bogus_id = uuid4()
    inserted: list[Any] = []

    async def fake_get_source(sid: UUID, *, pool: Any) -> dict[str, Any]:  # noqa: ARG001
        return _source_row(source_id=sid, role_project_id=uuid4())

    async def fake_list_by_ids(sid: UUID, ids: list[UUID], *, pool: Any) -> list[dict[str, Any]]:  # noqa: ARG001
        return [{"id": good_id, "platform_item_id": "p"}]  # bogus_id absent

    async def fake_insert_job(**kwargs: Any) -> UUID:
        inserted.append(kwargs)
        return uuid4()

    monkeypatch.setattr(sources_route.sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(sources_route.items_helper, "list_items_by_ids", fake_list_by_ids)
    monkeypatch.setattr(sources_route.jobs_helper, "insert_job", fake_insert_job)
    monkeypatch.setattr(sources_helper, "get_source", fake_get_source)
    monkeypatch.setattr(items_helper, "list_items_by_ids", fake_list_by_ids)
    monkeypatch.setattr(jobs_helper, "insert_job", fake_insert_job)
    _patch_owner(monkeypatch)

    resp = client.post(
        f"/api/sources/{source_id}/items/select",
        json={"item_ids": [str(good_id), str(bogus_id)]},
    )
    assert resp.status_code == 400
    assert inserted == []  # aucun job créé
