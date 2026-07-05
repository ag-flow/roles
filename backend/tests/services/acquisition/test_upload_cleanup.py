"""Tests de services.acquisition.upload.cleanup — nettoyage périodique des
slots présignés expirés (spec §5.5, critère §6 ligne 4 « item nettoyé »).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import asyncpg
import pytest

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.upload import cleanup, intake
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from tests.services.acquisition.conftest import TENANT_ID
from tests.services.acquisition.upload_helpers import FakeObjectStore

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 7, 5)
NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


async def _slot(pool: asyncpg.Pool, store: FakeObjectStore, request_key: str, *, now: datetime):
    return await intake.request_upload_slot(
        request_key=request_key,
        filename="conf.mp3",
        media_type="audio/mpeg",
        now=now,
        pool=pool,
        minio=store,
    )


async def test_cleanup_removes_only_expired_slots(pool: asyncpg.Pool) -> None:
    """Slot expiré supprimé (item + objet best-effort), slot valide intact."""
    store = FakeObjectStore()
    created = await intake.create_upload_request(
        title="Conf UX",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=TODAY,
        pool=pool,
    )
    expired = await _slot(pool, store, created["request_key"], now=NOW - timedelta(hours=3))
    fresh = await _slot(pool, store, created["request_key"], now=NOW)

    # Le PUT du slot expiré a eu lieu mais jamais le finalize : l'objet traîne.
    expired_item = await source_items_helper.get_by_id(expired["item_id"], pool=pool)
    store.objects[(AUDIO_BUCKET, expired_item["upload_s3_key"])] = b"orphan-bytes"

    removed = await cleanup.cleanup_expired_slots(now=NOW, pool=pool, minio=store)
    assert removed == 1

    assert await source_items_helper.get_by_id(expired["item_id"], pool=pool) is None
    assert (AUDIO_BUCKET, expired_item["upload_s3_key"]) not in store.objects
    assert await source_items_helper.get_by_id(fresh["item_id"], pool=pool) is not None


async def test_cleanup_ignores_finalized_items(pool: asyncpg.Pool) -> None:
    """Un item déjà sorti d'awaiting_upload n'est jamais nettoyé, même TTL passé."""
    store = FakeObjectStore()
    created = await intake.create_upload_request(
        title="Conf UX",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=TODAY,
        pool=pool,
    )
    slot = await _slot(pool, store, created["request_key"], now=NOW - timedelta(hours=3))
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    await source_items_helper.update_source_item_status(
        item["source_id"], item["platform_item_id"], "queued_transcription", pool=pool
    )

    removed = await cleanup.cleanup_expired_slots(now=NOW, pool=pool, minio=store)
    assert removed == 0
    assert await source_items_helper.get_by_id(slot["item_id"], pool=pool) is not None


async def test_cleanup_noop_when_nothing_expired(pool: asyncpg.Pool) -> None:
    store = FakeObjectStore()
    removed = await cleanup.cleanup_expired_slots(now=NOW, pool=pool, minio=store)
    assert removed == 0
    assert store.removed == []
