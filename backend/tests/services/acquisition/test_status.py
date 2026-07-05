"""Tests d'intégration — services.acquisition.status (roles__request_status,
roles__list_requests, §2.3)."""

from __future__ import annotations

from datetime import date

import asyncpg
import pytest

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.selection import select_items
from role_builder.services.acquisition.status import (
    compute_queue_position,
    list_requests,
    request_status,
)
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def _submit_discover_and_select(pool: asyncpg.Pool) -> tuple[str, str]:
    await insert_active_credential(pool, platform="youtube")
    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )
    request = await ar.get_by_key(result["request_key"], pool=pool)
    source_id = request["source_id"]
    await source_items_helper.insert_source_items_bulk(
        [
            {"id": "vid-1", "title": "T1", "duration_s": 100},
            {"id": "vid-2", "title": "T2", "duration_s": 200},
        ],
        source_id=source_id,
        tenant_id=TENANT_ID,
        pool=pool,
    )
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    await select_items(
        request_key=result["request_key"],
        item_ids=[r["id"] for r in rows],
        filters=None,
        pool=pool,
    )
    return result["request_key"], source_id


async def test_request_status_reports_counts_and_items(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_discover_and_select(pool)

    status = await request_status(request_key, pool=pool)

    assert status["request_key"] == request_key
    assert status["kind"] == "scrape"
    assert status["submitted_by"] == "claude-web"
    assert status["counts"]["discovered"] == 2
    assert status["counts"]["selected"] == 2
    assert status["counts"]["pending"] == 2  # les 2 items encore pending_download
    assert len(status["items"]) == 2
    assert status["cost"] == {"transcription_usd": 0.0}


async def test_request_status_acquiring_while_downloads_pending(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_discover_and_select(pool)
    status = await request_status(request_key, pool=pool)
    assert status["status"] == "acquiring"
    assert status["queue_position"] == 1  # un seul download job pending


async def test_request_status_discovering_before_any_item(pool: asyncpg.Pool) -> None:
    await insert_active_credential(pool, platform="youtube")
    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )

    status = await request_status(result["request_key"], pool=pool)

    assert status["status"] == "discovering"
    assert status["counts"]["discovered"] == 0
    assert "queue_position" in status  # un discover job est pending


async def test_request_status_raises_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await request_status("nope", pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"


async def test_compute_queue_position_none_when_nothing_pending(pool: asyncpg.Pool) -> None:
    from uuid import uuid4

    assert await compute_queue_position(uuid4(), pool=pool) is None


async def test_list_requests_returns_summaries(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_discover_and_select(pool)

    requests = await list_requests(pool=pool)

    matching = [r for r in requests if r["request_key"] == request_key]
    assert len(matching) == 1
    summary = matching[0]
    assert summary["kind"] == "scrape"
    assert summary["url"] == "https://youtube.com/@clea-ux"
    assert summary["submitted_by"] == "claude-web"
    assert summary["counts_summary"]["selected"] == 2


async def test_list_requests_filters_by_submitted_by(pool: asyncpg.Pool) -> None:
    await _submit_discover_and_select(pool)
    await insert_active_credential(pool, platform="tiktok")
    await submit_acquisition(
        url="https://tiktok.com/@other",
        submitted_by="other-agent",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )

    requests = await list_requests(submitted_by="other-agent", pool=pool)

    assert len(requests) == 1
    assert requests[0]["submitted_by"] == "other-agent"


async def test_multi_actor_queue_position_is_consistent(pool: asyncpg.Pool) -> None:
    """Deux submitted_by concurrents partagent la queue scraping sans se corrompre."""
    await insert_active_credential(pool, platform="youtube")
    first = await submit_acquisition(
        url="https://youtube.com/@first",
        submitted_by="agent-a",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )
    second = await submit_acquisition(
        url="https://youtube.com/@second",
        submitted_by="agent-b",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )

    status_first = await request_status(first["request_key"], pool=pool)
    status_second = await request_status(second["request_key"], pool=pool)

    # Le premier discover job soumis est en tête de queue (FIFO created_at ASC).
    assert status_first["queue_position"] == 1
    assert status_second["queue_position"] == 2

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    assert len(jobs) == 2
