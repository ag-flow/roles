"""Tests for routes.scraping_jobs — GET /api/scraping-jobs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


def _row(*, status: str = "pending") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": "discover",
        "status": status,
        "priority": 0,
        "attempts": 0,
        "error": None,
        "created_at": datetime.now(tz=UTC),
        "started_at": None,
        "completed_at": None,
    }


def test_get_scraping_jobs_forwards_status_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.db_helpers import scraping_jobs as jobs_helper
    from role_builder.routes import scraping_jobs as scraping_jobs_route

    captured: dict[str, Any] = {}

    async def fake_list(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [_row(status="pending")]

    monkeypatch.setattr(scraping_jobs_route.jobs_helper, "list_jobs", fake_list)
    monkeypatch.setattr(jobs_helper, "list_jobs", fake_list)

    resp = client.get("/api/scraping-jobs", params={"status": "pending", "limit": 25})
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "pending"
    assert captured["status"] == "pending"
    assert captured["limit"] == 25


def test_get_scraping_jobs_no_status_filter(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from role_builder.db_helpers import scraping_jobs as jobs_helper
    from role_builder.routes import scraping_jobs as scraping_jobs_route

    captured: dict[str, Any] = {}

    async def fake_list(**kwargs: Any) -> list[dict[str, Any]]:
        captured.update(kwargs)
        return [_row(status="done"), _row(status="pending")]

    monkeypatch.setattr(scraping_jobs_route.jobs_helper, "list_jobs", fake_list)
    monkeypatch.setattr(jobs_helper, "list_jobs", fake_list)

    resp = client.get("/api/scraping-jobs")
    assert resp.status_code == 200
    assert len(resp.json()) == 2
    assert captured["status"] is None
    assert captured["limit"] == 50
