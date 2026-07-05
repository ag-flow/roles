"""Tests d'intégration db_helpers.deposit_queue + db_helpers.corpus_pull_cursors.

`source_items` EST la queue de dépôt : status='transcribed' = pending,
claim par FOR UPDATE SKIP LOCKED (même pattern que les autres queues,
spec 01-data-model §9).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import asyncpg
import pytest

from role_builder.db_helpers import corpus_pull_cursors as cursors_helper
from role_builder.db_helpers import deposit_queue
from role_builder.db_helpers import source_items as source_items_helper
from tests.services.acquisition.conftest import TENANT_ID
from tests.services.deposit.helpers import insert_item, seed_request_with_item

pytestmark = pytest.mark.asyncio


async def test_claim_next_for_deposit_moves_item_to_depositing(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool, item_status="transcribed")

    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)

    assert claimed is not None
    assert claimed["id"] == seeded["item_id"]
    assert claimed["status"] == "depositing"
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "depositing"


async def test_claim_next_for_deposit_returns_none_when_empty(pool: asyncpg.Pool) -> None:
    await seed_request_with_item(pool, item_status="pending_download")

    assert await deposit_queue.claim_next_for_deposit(pool=pool) is None


async def test_claim_is_fifo_and_exclusive(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    second_id = await insert_item(pool, source_id=seeded["source_id"], status="transcribed")

    first_claim = await deposit_queue.claim_next_for_deposit(pool=pool)
    second_claim = await deposit_queue.claim_next_for_deposit(pool=pool)
    third_claim = await deposit_queue.claim_next_for_deposit(pool=pool)

    assert first_claim["id"] == seeded["item_id"]  # inséré en premier
    assert second_claim["id"] == second_id
    assert third_claim is None


async def test_mark_deposited_sets_refs_and_timestamp(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)

    await deposit_queue.mark_deposited(
        claimed["id"], doc_id="stub-abc123", slug="transcript-interview-ux-a1b2c3", pool=pool
    )

    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "deposited"
    assert row["docflow_doc_id"] == "stub-abc123"
    assert row["docflow_slug"] == "transcript-interview-ux-a1b2c3"
    assert row["deposited_at"] is not None
    assert row["error"] is None


async def test_mark_deposit_failed_keeps_transcript_and_sets_code(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool, transcript_s3_key="t/v2/src/vid-1.json")
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)

    await deposit_queue.mark_deposit_failed(claimed["id"], message="gateway timeout", pool=pool)

    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "failed"
    error = json.loads(row["error"])
    assert error["code"] == "DOCFLOW_DEPOSIT_FAILED"
    assert error["message"] == "gateway timeout"
    assert row["transcript_s3_key"] == "t/v2/src/vid-1.json"  # transcript conservé


async def test_requeue_stale_depositing(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    await deposit_queue.claim_next_for_deposit(pool=pool)

    requeued = await deposit_queue.requeue_stale_depositing(pool=pool)

    assert requeued == 1
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "transcribed"


async def test_list_deposited_for_source_with_since_and_provider(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO transcription_jobs (source_item_id, tenant_id, audio_s3_key, "
            "worker_pool_id, status, provider_used, completed_at) "
            "VALUES ($1, $2, 'a/vid.mp3', 'shared_default', 'done', 'faster-whisper', now())",
            seeded["item_id"],
            TENANT_ID,
        )
    claimed = await deposit_queue.claim_next_for_deposit(pool=pool)
    await deposit_queue.mark_deposited(claimed["id"], doc_id="d1", slug="s1", pool=pool)

    rows = await deposit_queue.list_deposited_for_source(seeded["source_id"], pool=pool)
    assert len(rows) == 1
    assert rows[0]["docflow_doc_id"] == "d1"
    assert rows[0]["provider_used"] == "faster-whisper"

    after = await deposit_queue.list_deposited_for_source(
        seeded["source_id"], since=rows[0]["deposited_at"], pool=pool
    )
    assert after == []  # strictement postérieur au curseur

    before = await deposit_queue.list_deposited_for_source(
        seeded["source_id"], since=datetime(2020, 1, 1, tzinfo=UTC), pool=pool
    )
    assert len(before) == 1


async def test_cursors_upsert_and_read_per_caller(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool)
    request_id = seeded["request_id"]
    t1 = datetime(2026, 7, 5, 10, 0, tzinfo=UTC)
    t2 = datetime(2026, 7, 5, 11, 0, tzinfo=UTC)

    assert await cursors_helper.get_last_pulled_at(request_id, "claude-web", pool=pool) is None

    await cursors_helper.upsert_cursor(request_id, "claude-web", t1, pool=pool)
    await cursors_helper.upsert_cursor(request_id, "agent-b", t2, pool=pool)
    assert await cursors_helper.get_last_pulled_at(request_id, "claude-web", pool=pool) == t1
    assert await cursors_helper.get_last_pulled_at(request_id, "agent-b", pool=pool) == t2

    await cursors_helper.upsert_cursor(request_id, "claude-web", t2, pool=pool)
    assert await cursors_helper.get_last_pulled_at(request_id, "claude-web", pool=pool) == t2
