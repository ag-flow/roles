"""Tests de services.acquisition.upload.intake — create_upload_request,
request_upload_slot, close_upload_request (spec v2/01-protocole-mcp.md §2.2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest

from role_builder.db_helpers import acquisition_requests as ar
from role_builder.db_helpers import source_items as source_items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.upload import intake
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from tests.services.acquisition.conftest import TENANT_ID
from tests.services.acquisition.upload_helpers import FakeObjectStore

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 7, 5)
NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


async def _create_request(pool: asyncpg.Pool, *, title: str = "Conférence UX interne") -> str:
    created = await intake.create_upload_request(
        title=title,
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=TODAY,
        pool=pool,
    )
    return created["request_key"]


async def test_create_upload_request_nominal(pool: asyncpg.Pool) -> None:
    """create_upload_request → requête kind=upload ouverte, source technique sans URL."""
    created = await intake.create_upload_request(
        title="Conférence UX interne",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=TODAY,
        pool=pool,
    )
    assert created["status"] == "open_for_upload"
    # _slugify ne translittère pas les accents (comportement partagé avec le scrape).
    assert created["request_key"].startswith("up-conf-rence-ux-interne-2026-07-05")

    request = await ar.get_by_key(created["request_key"], pool=pool)
    assert request["kind"] == "upload"
    assert request["status"] == "open_for_upload"
    assert request["submitted_by"] == "claude-web"

    source = await sources_helper.get_source(request["source_id"], pool=pool)
    assert source["platform"] == "upload"
    assert source["url"] is None


async def test_request_upload_slot_nominal(pool: asyncpg.Pool) -> None:
    """request_upload_slot → item awaiting_upload sélectionné + URL présignée PUT, TTL 1 h."""
    store = FakeObjectStore()
    request_key = await _create_request(pool)

    slot = await intake.request_upload_slot(
        request_key=request_key,
        filename="conf-ux.mp3",
        media_type="audio/mpeg",
        title="Conf UX : plénière",
        duration_s=1800,
        now=NOW,
        pool=pool,
        minio=store,
    )
    assert slot["upload_url"].startswith("https://")
    assert slot["expires_at"] == (NOW + timedelta(hours=1)).isoformat()

    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    assert item["status"] == "awaiting_upload"
    assert item["selected"] is True
    assert item["title"] == "Conf UX : plénière"
    assert item["duration_s"] == 1800
    assert item["upload_media_type"] == "audio/mpeg"
    assert item["upload_s3_key"].startswith(f"upload/{request_key}/")
    assert item["upload_s3_key"].endswith(".mp3")
    assert item["upload_expires_at"] == NOW + timedelta(hours=1)

    bucket, key, ttl = store.presigned_puts[0]
    assert bucket == AUDIO_BUCKET
    assert key == item["upload_s3_key"]
    assert ttl == 3600


async def test_request_upload_slot_title_defaults_to_filename(pool: asyncpg.Pool) -> None:
    request_key = await _create_request(pool)
    slot = await intake.request_upload_slot(
        request_key=request_key,
        filename="enregistrement.wav",
        media_type="audio/wav",
        now=NOW,
        pool=pool,
        minio=FakeObjectStore(),
    )
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    assert item["title"] == "enregistrement.wav"


async def test_request_upload_slot_unsupported_media(pool: asyncpg.Pool) -> None:
    request_key = await _create_request(pool)
    with pytest.raises(AcquisitionError) as excinfo:
        await intake.request_upload_slot(
            request_key=request_key,
            filename="slides.pdf",
            media_type="application/pdf",
            now=NOW,
            pool=pool,
            minio=FakeObjectStore(),
        )
    assert excinfo.value.code == "UNSUPPORTED_MEDIA"


async def test_request_upload_slot_unknown_request(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as excinfo:
        await intake.request_upload_slot(
            request_key="up-inconnu-2026-07-05",
            filename="a.mp3",
            media_type="audio/mpeg",
            now=NOW,
            pool=pool,
            minio=FakeObjectStore(),
        )
    assert excinfo.value.code == "UNKNOWN_REQUEST"


async def test_request_upload_slot_rejects_scrape_request(pool: asyncpg.Pool) -> None:
    """Une requête kind=scrape n'est pas une requête d'upload."""
    source_id = await sources_helper.insert_source(
        role_project_id=None,
        tenant_id=TENANT_ID,
        platform="youtube",
        source_type="channel",
        url="https://youtube.com/@clea-ux",
        pool=pool,
    )
    await ar.insert_request(
        request_key="yt-clea-ux-2026-07-05",
        tenant_id=TENANT_ID,
        submitted_by="claude-web",
        kind="scrape",
        source_id=source_id,
        mode="auto",
        filters=None,
        docflow_target=None,
        note=None,
        status="acquiring",
        pool=pool,
    )
    with pytest.raises(AcquisitionError) as excinfo:
        await intake.request_upload_slot(
            request_key="yt-clea-ux-2026-07-05",
            filename="a.mp3",
            media_type="audio/mpeg",
            now=NOW,
            pool=pool,
            minio=FakeObjectStore(),
        )
    assert excinfo.value.code == "UNKNOWN_REQUEST"


async def test_request_upload_slot_on_closed_request(pool: asyncpg.Pool) -> None:
    request_key = await _create_request(pool)
    await intake.close_upload_request(request_key=request_key, pool=pool)

    with pytest.raises(AcquisitionError) as excinfo:
        await intake.request_upload_slot(
            request_key=request_key,
            filename="a.mp3",
            media_type="audio/mpeg",
            now=NOW,
            pool=pool,
            minio=FakeObjectStore(),
        )
    assert excinfo.value.code == "REQUEST_CLOSED"


async def test_close_upload_request_is_idempotent(pool: asyncpg.Pool) -> None:
    """close → acquiring ; un second close ne change rien."""
    request_key = await _create_request(pool)

    first = await intake.close_upload_request(request_key=request_key, pool=pool)
    assert first == {"request_key": request_key, "status": "acquiring"}

    second = await intake.close_upload_request(request_key=request_key, pool=pool)
    assert second == {"request_key": request_key, "status": "acquiring"}


async def test_close_upload_request_unknown(pool: asyncpg.Pool) -> None:
    with pytest.raises(AcquisitionError) as excinfo:
        await intake.close_upload_request(request_key="up-inconnu-2026-07-05", pool=pool)
    assert excinfo.value.code == "UNKNOWN_REQUEST"


async def test_request_upload_slot_published_at_parsed(pool: asyncpg.Pool) -> None:
    request_key = await _create_request(pool)
    slot = await intake.request_upload_slot(
        request_key=request_key,
        filename="conf.mp3",
        media_type="audio/mpeg",
        published_at="2026-03-14T10:00:00+00:00",
        now=NOW,
        pool=pool,
        minio=FakeObjectStore(),
    )
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    assert item["published_at"] == datetime(2026, 3, 14, 10, 0, 0, tzinfo=UTC)


async def test_request_upload_slot_published_at_invalid(pool: asyncpg.Pool) -> None:
    request_key = await _create_request(pool)
    with pytest.raises(AcquisitionError) as excinfo:
        await intake.request_upload_slot(
            request_key=request_key,
            filename="conf.mp3",
            media_type="audio/mpeg",
            published_at="pas-une-date",
            now=NOW,
            pool=pool,
            minio=FakeObjectStore(),
        )
    assert excinfo.value.code == "INVALID_PUBLISHED_AT"
