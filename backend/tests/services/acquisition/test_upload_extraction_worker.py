"""Tests de services.acquisition.upload.extraction_worker — extraction audio
asynchrone des uploads vidéo (spec §2.2, §1.1).

Le finalize d'un upload vidéo pose l'item en `pending_extraction` ; c'est ce
worker (et non l'appel MCP) qui fait le ffmpeg, puis l'entrée en transcription.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import asyncpg
import pytest

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.upload import extraction_worker as worker_mod
from role_builder.services.acquisition.upload import finalize as finalize_mod
from role_builder.services.acquisition.upload import intake
from role_builder.services.acquisition.upload.extraction_worker import AudioExtractionWorker
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from tests.services.acquisition.conftest import TENANT_ID
from tests.services.acquisition.upload_helpers import FakeObjectStore, make_fake_extractor

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 7, 5)
NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


async def _video_slot_finalized(
    pool: asyncpg.Pool, store: FakeObjectStore
) -> dict[str, Any]:
    """Crée un upload vidéo, simule le PUT, puis finalize → `pending_extraction`."""
    created = await intake.create_upload_request(
        title="Conf UX", submitted_by="claude-web", tenant_id=TENANT_ID, today=TODAY, pool=pool
    )
    slot = await intake.request_upload_slot(
        request_key=created["request_key"],
        filename="conf.mp4",
        media_type="video/mp4",
        now=NOW,
        pool=pool,
        minio=store,
    )
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    store.objects[(AUDIO_BUCKET, item["upload_s3_key"])] = b"video-bytes"
    result = await finalize_mod.finalize_upload(
        request_key=created["request_key"], item_id=slot["item_id"], now=NOW, pool=pool, minio=store
    )
    assert result["status"] == "pending_extraction"
    return {"item_id": slot["item_id"], "upload_s3_key": item["upload_s3_key"]}


async def _transcription_jobs_for(pool: asyncpg.Pool, item_id: Any) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM transcription_jobs WHERE source_item_id = $1", item_id
        )
    return [dict(r) for r in rows]


async def test_worker_extracts_and_enters_pipeline(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """tick() : pending_extraction → audio_ready+job+queued_transcription, brut supprimé."""
    store = FakeObjectStore()
    ctx = await _video_slot_finalized(pool, store)

    extractor = make_fake_extractor(store)
    monkeypatch.setattr(worker_mod, "extract_audio_to_mp3", extractor)

    worker = AudioExtractionWorker(pool=pool, minio=store, max_attempts=2, backoff_base_s=0.0)
    assert await worker.tick() is True

    expected_audio_key = ctx["upload_s3_key"].rsplit(".", 1)[0] + ".mp3"
    assert extractor.calls == [(AUDIO_BUCKET, ctx["upload_s3_key"], expected_audio_key)]

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "queued_transcription"
    assert item["audio_s3_key"] == expected_audio_key
    # Le brut vidéo est supprimé, seul l'audio extrait reste.
    assert (AUDIO_BUCKET, ctx["upload_s3_key"]) not in store.objects
    assert (AUDIO_BUCKET, expected_audio_key) in store.objects

    jobs = await _transcription_jobs_for(pool, ctx["item_id"])
    assert len(jobs) == 1
    assert jobs[0]["audio_s3_key"] == expected_audio_key
    assert jobs[0]["worker_pool_id"] == "shared_default"


async def test_worker_tick_empty_queue_returns_false(pool: asyncpg.Pool) -> None:
    worker = AudioExtractionWorker(pool=pool, minio=FakeObjectStore())
    assert await worker.tick() is False


async def test_worker_extraction_failure_marks_item_failed(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Échec ffmpeg après épuisement des tentatives → item failed, pas de job."""
    store = FakeObjectStore()
    ctx = await _video_slot_finalized(pool, store)

    monkeypatch.setattr(worker_mod, "extract_audio_to_mp3", make_fake_extractor(store, fail=True))

    worker = AudioExtractionWorker(pool=pool, minio=store, max_attempts=2, backoff_base_s=0.0)
    assert await worker.tick() is True

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "failed"
    assert "AUDIO_EXTRACTION_FAILED" in item["error"]
    assert await _transcription_jobs_for(pool, ctx["item_id"]) == []


async def test_recover_requeues_stale_extracting(pool: asyncpg.Pool) -> None:
    """Un item resté `extracting_audio` (crash mid-ffmpeg) est remis en queue."""
    store = FakeObjectStore()
    ctx = await _video_slot_finalized(pool, store)
    # Simule un claim interrompu par un crash : l'item reste extracting_audio.
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE source_items SET status = 'extracting_audio' WHERE id = $1", ctx["item_id"]
        )

    worker = AudioExtractionWorker(pool=pool, minio=store)
    assert await worker.recover() == 1

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "pending_extraction"


async def test_reextraction_does_not_duplicate_job(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reprise crash : ré-extraire un item déjà pourvu d'un job n'en crée pas un second."""
    store = FakeObjectStore()
    ctx = await _video_slot_finalized(pool, store)
    monkeypatch.setattr(worker_mod, "extract_audio_to_mp3", make_fake_extractor(store))

    worker = AudioExtractionWorker(pool=pool, minio=store, max_attempts=2, backoff_base_s=0.0)
    await worker.tick()

    # L'item est requeué (comme après un crash) puis retraité.
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE source_items SET status = 'pending_extraction' WHERE id = $1", ctx["item_id"]
        )
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"video-bytes"  # brut re-présent
    assert await worker.tick() is True

    assert len(await _transcription_jobs_for(pool, ctx["item_id"])) == 1
