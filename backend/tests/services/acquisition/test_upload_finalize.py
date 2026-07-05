"""Tests de services.acquisition.upload.finalize — vérification objet MinIO,
extraction audio si vidéo, entrée dans le pipeline standard (spec §2.2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import pytest

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.acquisition.errors import AcquisitionError
from role_builder.services.acquisition.upload import finalize as finalize_mod
from role_builder.services.acquisition.upload import intake
from role_builder.services.acquisition.upload.intake import AUDIO_BUCKET
from tests.services.acquisition.conftest import TENANT_ID
from tests.services.acquisition.upload_helpers import FakeObjectStore, make_fake_extractor

pytestmark = pytest.mark.asyncio

TODAY = date(2026, 7, 5)
NOW = datetime(2026, 7, 5, 12, 0, 0, tzinfo=UTC)


async def _request_with_slot(
    pool: asyncpg.Pool,
    store: FakeObjectStore,
    *,
    media_type: str = "audio/mpeg",
    filename: str = "conf.mp3",
) -> dict[str, Any]:
    created = await intake.create_upload_request(
        title="Conf UX",
        submitted_by="claude-web",
        tenant_id=TENANT_ID,
        today=TODAY,
        pool=pool,
    )
    slot = await intake.request_upload_slot(
        request_key=created["request_key"],
        filename=filename,
        media_type=media_type,
        now=NOW,
        pool=pool,
        minio=store,
    )
    item = await source_items_helper.get_by_id(slot["item_id"], pool=pool)
    return {
        "request_key": created["request_key"],
        "item_id": slot["item_id"],
        "upload_s3_key": item["upload_s3_key"],
    }


async def _transcription_jobs_for(pool: asyncpg.Pool, item_id: UUID) -> list[dict[str, Any]]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM transcription_jobs WHERE source_item_id = $1", item_id
        )
    return [dict(r) for r in rows]


async def test_finalize_audio_nominal(pool: asyncpg.Pool) -> None:
    """PUT présent → item queued_transcription, job de transcription en queue partagée."""
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store)
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"audio-bytes"

    result = await finalize_mod.finalize_upload(
        request_key=ctx["request_key"],
        item_id=ctx["item_id"],
        now=NOW,
        pool=pool,
        minio=store,
    )
    assert result == {"item_id": ctx["item_id"], "status": "queued_transcription"}

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "queued_transcription"
    assert item["audio_s3_key"] == ctx["upload_s3_key"]

    jobs = await _transcription_jobs_for(pool, ctx["item_id"])
    assert len(jobs) == 1
    assert jobs[0]["audio_s3_key"] == ctx["upload_s3_key"]
    assert jobs[0]["worker_pool_id"] == "shared_default"
    assert jobs[0]["status"] == "pending"


async def test_finalize_video_extracts_audio(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """media_type vidéo → extraction ffmpeg : audio_s3_key = mp3 extrait, brut supprimé."""
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store, media_type="video/mp4", filename="conf.mp4")
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"video-bytes"

    extractor = make_fake_extractor(store)
    monkeypatch.setattr(finalize_mod, "extract_audio_to_mp3", extractor)

    result = await finalize_mod.finalize_upload(
        request_key=ctx["request_key"],
        item_id=ctx["item_id"],
        now=NOW,
        pool=pool,
        minio=store,
    )
    assert result["status"] == "queued_transcription"

    expected_audio_key = ctx["upload_s3_key"].rsplit(".", 1)[0] + ".mp3"
    assert extractor.calls == [(AUDIO_BUCKET, ctx["upload_s3_key"], expected_audio_key)]

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["audio_s3_key"] == expected_audio_key
    # L'objet vidéo brut est supprimé après extraction (seul l'audio est conservé).
    assert (AUDIO_BUCKET, ctx["upload_s3_key"]) not in store.objects
    assert (AUDIO_BUCKET, expected_audio_key) in store.objects

    jobs = await _transcription_jobs_for(pool, ctx["item_id"])
    assert jobs[0]["audio_s3_key"] == expected_audio_key


async def test_finalize_video_extraction_failure_marks_item_failed(
    pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store, media_type="video/mp4", filename="conf.mp4")
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"video-bytes"

    monkeypatch.setattr(finalize_mod, "extract_audio_to_mp3", make_fake_extractor(store, fail=True))

    with pytest.raises(AcquisitionError) as excinfo:
        await finalize_mod.finalize_upload(
            request_key=ctx["request_key"],
            item_id=ctx["item_id"],
            now=NOW,
            pool=pool,
            minio=store,
        )
    assert excinfo.value.code == "AUDIO_EXTRACTION_FAILED"

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "failed"
    assert "AUDIO_EXTRACTION_FAILED" in item["error"]
    assert await _transcription_jobs_for(pool, ctx["item_id"]) == []


async def test_finalize_without_put_raises_upload_not_found(pool: asyncpg.Pool) -> None:
    """PUT absent (slot encore valide) → UPLOAD_NOT_FOUND, item conservé."""
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store)

    with pytest.raises(AcquisitionError) as excinfo:
        await finalize_mod.finalize_upload(
            request_key=ctx["request_key"],
            item_id=ctx["item_id"],
            now=NOW,
            pool=pool,
            minio=store,
        )
    assert excinfo.value.code == "UPLOAD_NOT_FOUND"

    item = await source_items_helper.get_by_id(ctx["item_id"], pool=pool)
    assert item["status"] == "awaiting_upload"  # le client peut refaire son PUT


async def test_finalize_expired_slot_cleans_item(pool: asyncpg.Pool) -> None:
    """Critère §6 ligne 4 : slot expiré → UPLOAD_EXPIRED ; item nettoyé."""
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store)
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"audio-bytes"

    with pytest.raises(AcquisitionError) as excinfo:
        await finalize_mod.finalize_upload(
            request_key=ctx["request_key"],
            item_id=ctx["item_id"],
            now=NOW + timedelta(hours=2),
            pool=pool,
            minio=store,
        )
    assert excinfo.value.code == "UPLOAD_EXPIRED"

    assert await source_items_helper.get_by_id(ctx["item_id"], pool=pool) is None
    assert (AUDIO_BUCKET, ctx["upload_s3_key"]) not in store.objects


async def test_finalize_is_idempotent(pool: asyncpg.Pool) -> None:
    """Un second finalize ne recrée pas de job et rend le statut courant."""
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store)
    store.objects[(AUDIO_BUCKET, ctx["upload_s3_key"])] = b"audio-bytes"

    await finalize_mod.finalize_upload(
        request_key=ctx["request_key"], item_id=ctx["item_id"], now=NOW, pool=pool, minio=store
    )
    second = await finalize_mod.finalize_upload(
        request_key=ctx["request_key"], item_id=ctx["item_id"], now=NOW, pool=pool, minio=store
    )
    assert second == {"item_id": ctx["item_id"], "status": "queued_transcription"}
    assert len(await _transcription_jobs_for(pool, ctx["item_id"])) == 1


async def test_finalize_unknown_item_raises_upload_not_found(pool: asyncpg.Pool) -> None:
    store = FakeObjectStore()
    ctx = await _request_with_slot(pool, store)

    with pytest.raises(AcquisitionError) as excinfo:
        await finalize_mod.finalize_upload(
            request_key=ctx["request_key"],
            item_id=UUID("00000000-0000-0000-0000-00000000dead"),
            now=NOW,
            pool=pool,
            minio=store,
        )
    assert excinfo.value.code == "UPLOAD_NOT_FOUND"
