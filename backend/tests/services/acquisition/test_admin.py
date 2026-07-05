"""Tests d'intégration — services.acquisition.admin (roles__cancel_request,
roles__retry_failed, §2.5)."""

from __future__ import annotations

from datetime import date

import asyncpg
import pytest

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import deposit_queue
from role_builder.db_helpers import scraping_jobs as scraping_jobs_helper
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.admin import cancel_request, retry_failed
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.selection import select_items
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def _submit_discover_and_select(pool: asyncpg.Pool, *, item_count: int = 2) -> tuple[str, str]:
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
    items = [{"id": f"vid-{i}", "title": f"T{i}", "duration_s": 100} for i in range(item_count)]
    await source_items_helper.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=TENANT_ID, pool=pool
    )
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    await select_items(
        request_key=result["request_key"],
        item_ids=[r["id"] for r in rows],
        filters=None,
        pool=pool,
    )
    return result["request_key"], source_id


async def _fail_download_job_for_item(item_id, *, pool: asyncpg.Pool) -> None:
    """Simule ce que fait l'orchestrator réel : le job échoue avant que l'item ne
    passe 'failed' (un item failed n'a jamais de job download encore actif)."""
    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    job = next(j for j in jobs if j["source_item_id"] == item_id and j["command"] == "download")
    await scraping_jobs_helper.mark_job_failed(job["id"], "boom", pool=pool)


async def test_cancel_request_cancels_pending_jobs(pool: asyncpg.Pool) -> None:
    request_key, source_id = await _submit_discover_and_select(pool, item_count=2)

    result = await cancel_request(request_key, note="plus besoin", pool=pool)

    # 1 discover job (créé par submit_acquisition) + 2 download jobs (select_items).
    assert result["cancelled_jobs"] == 3
    assert result["deposited_kept"] == 0

    updated = await ar.get_by_key(request_key, pool=pool)
    assert updated["status"] == "cancelled"

    remaining_pending = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    assert [j for j in remaining_pending if j["source_id"] == source_id] == []


async def test_cancel_request_preserves_deposited_items(pool: asyncpg.Pool) -> None:
    """Les items déjà déposés restent inchangés par cancel (§2.5)."""
    request_key, source_id = await _submit_discover_and_select(pool, item_count=2)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    # Simule un item déjà déposé avant l'annulation (le pipeline de dépôt est hors lot,
    # mais cancel_request doit rester correct une fois le lot 4 branché).
    await source_items_helper.update_source_item_status(
        source_id, rows[0]["platform_item_id"], "deposited", pool=pool
    )

    result = await cancel_request(request_key, note=None, pool=pool)

    assert result["deposited_kept"] == 1
    deposited_status = await source_items_helper.get_by_id(rows[0]["id"], pool=pool)
    assert deposited_status["status"] == "deposited"


async def test_cancel_request_raises_already_cancelled(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_discover_and_select(pool)
    await cancel_request(request_key, note=None, pool=pool)

    with pytest.raises(AcquisitionError) as exc_info:
        await cancel_request(request_key, note=None, pool=pool)
    assert exc_info.value.code == "ALREADY_CANCELLED"


async def test_cancel_request_raises_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await cancel_request("nope", note=None, pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"


async def test_retry_failed_requeues_failed_items(pool: asyncpg.Pool) -> None:
    request_key, source_id = await _submit_discover_and_select(pool, item_count=2)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    await _fail_download_job_for_item(rows[0]["id"], pool=pool)
    await source_items_helper.update_source_item_status(
        source_id, rows[0]["platform_item_id"], "failed", error="geo-restricted", pool=pool
    )

    result = await retry_failed(request_key, item_ids=None, pool=pool)

    assert result["retried_count"] == 1
    reset_item = await source_items_helper.get_by_id(rows[0]["id"], pool=pool)
    assert reset_item["status"] == "pending_download"
    assert reset_item["error"] is None

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    download_jobs_for_item = [
        j for j in jobs if j["source_item_id"] == rows[0]["id"] and j["command"] == "download"
    ]
    assert len(download_jobs_for_item) == 1


async def test_retry_failed_with_explicit_item_ids_subset(pool: asyncpg.Pool) -> None:
    request_key, source_id = await _submit_discover_and_select(pool, item_count=2)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    for row in rows:
        await _fail_download_job_for_item(row["id"], pool=pool)
        await source_items_helper.update_source_item_status(
            source_id, row["platform_item_id"], "failed", error="boom", pool=pool
        )

    result = await retry_failed(request_key, item_ids=[rows[0]["id"]], pool=pool)

    assert result["retried_count"] == 1
    other_item = await source_items_helper.get_by_id(rows[1]["id"], pool=pool)
    assert other_item["status"] == "failed"  # non demandé, pas retenté


async def test_retry_failed_deposit_failure_returns_to_transcribed(pool: asyncpg.Pool) -> None:
    """Critère §6 ligne 7 : un item échoué au dépôt docflow (transcript conservé
    dans MinIO) repart en 'transcribed' — pas de re-download, pas de nouveau
    scraping job — pour que le worker de dépôt le reprenne."""
    request_key, source_id = await _submit_discover_and_select(pool, item_count=1)
    rows = await source_items_helper.list_items_by_source(source_id, limit=10, offset=0, pool=pool)
    item = rows[0]

    # Simule le pipeline réel : download done, transcript produit, dépôt échoué.
    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    for job in jobs:
        if job["source_item_id"] == item["id"]:
            await scraping_jobs_helper.mark_job_done(job["id"], pool=pool)
    await source_items_helper.update_source_item_status(
        source_id,
        item["platform_item_id"],
        "transcribed",
        transcript_s3_key="t/vid-0.json",
        pool=pool,
    )
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)
    await deposit_queue.mark_deposit_failed(claimed["id"], message="gateway down", pool=pool)

    result = await retry_failed(request_key, item_ids=None, pool=pool)

    assert result["retried_count"] == 1
    reset_item = await source_items_helper.get_by_id(item["id"], pool=pool)
    assert reset_item["status"] == "transcribed"
    assert reset_item["error"] is None
    assert reset_item["transcript_s3_key"] == "t/vid-0.json"

    jobs = await scraping_jobs_helper.list_jobs(status="pending", pool=pool)
    assert not [j for j in jobs if j["source_item_id"] == item["id"]]  # pas de re-download


async def test_retry_failed_raises_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await retry_failed("nope", item_ids=None, pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"
