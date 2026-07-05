"""Tests d'intégration — services.acquisition.discovery.list_discovered (§2.1)."""

from __future__ import annotations

from datetime import UTC, date, datetime

import asyncpg
import pytest

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.discovery import list_discovered
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.submission import submit_acquisition
from tests.services.acquisition.conftest import TENANT_ID, insert_active_credential

pytestmark = pytest.mark.asyncio


async def _submit_and_discover(pool: asyncpg.Pool, *, item_count: int = 3) -> tuple[str, str]:
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

    items = [
        {
            "id": f"vid-{i}",
            "title": f"Video {i}",
            "duration_s": 100,
            "description_excerpt": f"Extrait {i}",
            "tags": ["ux"],
            "published_at": datetime(2026, 1, i + 1, tzinfo=UTC),
        }
        for i in range(item_count)
    ]
    await source_items_helper.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=TENANT_ID, pool=pool
    )
    from role_builder.db_helpers import sources as sources_helper

    await sources_helper.update_source_status(
        source_id, "discovered", discovered_count=item_count, pool=pool
    )
    return result["request_key"], source_id


async def test_list_discovered_returns_rich_metadata(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_and_discover(pool, item_count=2)

    result = await list_discovered(request_key=request_key, cursor=None, limit=50, pool=pool)

    assert result["request_key"] == request_key
    assert result["discovery_complete"] is True
    assert result["next_cursor"] is None
    assert len(result["items"]) == 2
    item = result["items"][0]
    assert set(item.keys()) == {
        "item_id",
        "title",
        "description_excerpt",
        "tags",
        "duration_s",
        "published_at",
        "thumbnail_url",
        "already_selected",
    }
    assert item["tags"] == ["ux"]
    assert item["already_selected"] is False


async def test_list_discovered_paginates_with_cursor(pool: asyncpg.Pool) -> None:
    request_key, _source_id = await _submit_and_discover(pool, item_count=5)

    first_page = await list_discovered(request_key=request_key, cursor=None, limit=2, pool=pool)
    assert len(first_page["items"]) == 2
    assert first_page["next_cursor"] is not None

    second_page = await list_discovered(
        request_key=request_key, cursor=first_page["next_cursor"], limit=2, pool=pool
    )
    assert len(second_page["items"]) == 2

    first_ids = {i["item_id"] for i in first_page["items"]}
    second_ids = {i["item_id"] for i in second_page["items"]}
    assert first_ids.isdisjoint(second_ids)


async def test_list_discovered_partial_during_discovery(pool: asyncpg.Pool) -> None:
    """discovery_complete=False tant que la source n'est pas passée 'discovered'."""
    await insert_active_credential(pool, platform="youtube")
    result = await submit_acquisition(
        url="https://youtube.com/@clea-ux",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=date(2026, 7, 5),
        pool=pool,
    )
    request = await ar.get_by_key(result["request_key"], pool=pool)

    partial = await list_discovered(
        request_key=result["request_key"], cursor=None, limit=50, pool=pool
    )
    assert partial["discovery_complete"] is False
    assert partial["items"] == []
    assert request["status"] == "discovering"


async def test_list_discovered_raises_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as exc_info:
        await list_discovered(request_key="nope", cursor=None, limit=50, pool=pool)
    assert exc_info.value.code == "UNKNOWN_REQUEST"
