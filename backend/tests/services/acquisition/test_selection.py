"""Tests d'intégration — services.acquisition.selection (roles__select_items, §2.1)."""

from __future__ import annotations

from datetime import date

import asyncpg
import pytest

from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.selection import select_items
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def _submit_and_discover(pool: asyncpg.Pool, *, item_count: int = 3) -> tuple[str, str]:
    """Soumet une acquisition puis simule la découverte (comme le ferait le scraper)."""
    await insert_active_credential(pool, platform="youtube")
    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )
    from role_builder.db_helpers import acquisition_requests as ar

    request = await ar.get_by_key(result["request_key"], pool=pool)
    source_id = request["source_id"]

    items = [
        {"id": f"vid-{i}", "title": f"Video {i}", "duration_s": 100 * (i + 1)}
        for i in range(item_count)
    ]
    await source_items_helper.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=TENANT_ID, pool=pool
    )
    return result["request_key"], source_id


async def test_select_items_by_ids_marks_selected_and_queues_download(
    pool: asyncpg.Pool,
) -> None:
    request_key, source_id = await _submit_and_discover(pool)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    chosen = [rows[0]["id"], rows[1]["id"]]

    result = await select_items(request_key=request_key, item_ids=chosen, filters=None, pool=pool)

    assert result == {"selected_count": 2, "queued_count": 2}

    selected_rows = await source_items_helper.list_items_by_source(
        source_id, selected=True, limit=10, offset=0, pool=pool
    )
    assert {r["id"] for r in selected_rows} == set(chosen)

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    download_jobs = [j for j in jobs if j["command"] == "download"]
    assert len(download_jobs) == 2


async def test_select_items_is_idempotent_no_duplicate_jobs(pool: asyncpg.Pool) -> None:
    """Rappeler select_items avec les mêmes item_ids ne recrée pas de download job."""
    request_key, source_id = await _submit_and_discover(pool)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    chosen = [rows[0]["id"]]

    first = await select_items(request_key=request_key, item_ids=chosen, filters=None, pool=pool)
    second = await select_items(request_key=request_key, item_ids=chosen, filters=None, pool=pool)

    assert first["queued_count"] == 1
    assert second["queued_count"] == 0  # déjà un job actif pour cet item
    assert second["selected_count"] == 1  # toujours idempotent côté sélection

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    download_jobs = [j for j in jobs if j["command"] == "download"]
    assert len(download_jobs) == 1


async def test_select_items_is_cumulable_across_calls(pool: asyncpg.Pool) -> None:
    """Deux appels avec des item_ids différents cumulent la sélection (pas de deselect)."""
    request_key, source_id = await _submit_and_discover(pool, item_count=3)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)

    await select_items(request_key=request_key, item_ids=[rows[0]["id"]], filters=None, pool=pool)
    await select_items(request_key=request_key, item_ids=[rows[1]["id"]], filters=None, pool=pool)

    selected_rows = await source_items_helper.list_items_by_source(
        source_id, selected=True, limit=10, offset=0, pool=pool
    )
    assert {r["id"] for r in selected_rows} == {rows[0]["id"], rows[1]["id"]}


async def test_select_items_with_filters_selects_matching_only(pool: asyncpg.Pool) -> None:
    """filters (sans item_ids) sélectionne les items correspondants (ex. min_duration_s)."""
    request_key, source_id = await _submit_and_discover(pool, item_count=3)
    # durations générées : 100, 200, 300 — filtre >= 200 doit prendre les 2 derniers

    result = await select_items(
        request_key=request_key, item_ids=None, filters={"min_duration_s": 200}, pool=pool
    )

    assert result["selected_count"] == 2
    selected_rows = await source_items_helper.list_items_by_source(
        source_id, selected=True, limit=10, offset=0, pool=pool
    )
    assert all(r["duration_s"] >= 200 for r in selected_rows)


async def test_select_items_raises_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await select_items(request_key="does-not-exist", item_ids=[], filters=None, pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"
