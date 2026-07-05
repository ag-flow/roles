"""Tests d'intégration — services.acquisition.auto_select.on_discovery_complete.

Hook appelé par event_handlers sur l'event 'discovered' (branche la
sélection automatique du mode=auto sur le pipeline scraper existant).
"""

from __future__ import annotations

from datetime import date

import asyncpg
import pytest

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.auto_select import on_discovery_complete
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def test_on_discovery_complete_auto_mode_selects_and_queues(pool: asyncpg.Pool) -> None:
    await insert_active_credential(pool, platform="youtube")
    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        mode="auto",
        filters={"min_duration_s": 200},
        today=date(2026, 7, 5),
        pool=pool,
    )
    request = await ar.get_by_key(result["request_key"], pool=pool)
    source_id = request["source_id"]

    items = [
        {"id": "vid-1", "title": "T1", "duration_s": 100},
        {"id": "vid-2", "title": "T2", "duration_s": 300},
    ]
    await source_items_helper.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=TENANT_ID, pool=pool
    )

    await on_discovery_complete(request, source_id=source_id, tenant_id=TENANT_ID, pool=pool)

    updated = await ar.get_by_key(result["request_key"], pool=pool)
    assert updated["status"] == "acquiring"

    selected_rows = await source_items_helper.list_items_by_source(
        source_id, selected=True, limit=10, offset=0, pool=pool
    )
    assert len(selected_rows) == 1
    assert selected_rows[0]["duration_s"] == 300

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    download_jobs = [j for j in jobs if j["command"] == "download"]
    assert len(download_jobs) == 1


async def test_on_discovery_complete_discover_only_mode_just_marks_discovered(
    pool: asyncpg.Pool,
) -> None:
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
        [{"id": "vid-1", "title": "T1", "duration_s": 100}],
        source_id=source_id,
        tenant_id=TENANT_ID,
        pool=pool,
    )

    await on_discovery_complete(request, source_id=source_id, tenant_id=TENANT_ID, pool=pool)

    updated = await ar.get_by_key(result["request_key"], pool=pool)
    assert updated["status"] == "discovered"

    selected_rows = await source_items_helper.list_items_by_source(
        source_id, selected=True, limit=10, offset=0, pool=pool
    )
    assert selected_rows == []
