"""Tests d'intégration du DepositWorker (transcribed → depositing → deposited).

MinIO est remplacé par un fake en mémoire (le pivot JSON y est servi) ;
la DB est réelle (fixture pool). Le backoff est mis à 0 pour les tests.
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg
import pytest

from role_builder.db_helpers import source_items as source_items_helper
from role_builder.services.deposit.base import DepositResult
from role_builder.services.deposit.stub import StubDepositor
from role_builder.services.deposit.worker import DepositWorker
from tests.services.deposit.helpers import FakeMinio, make_pivot, seed_request_with_item

pytestmark = pytest.mark.asyncio

_PIVOT = make_pivot(
    " Bonjour, dans cette vidéo…", "on observe avant de questionner. "
)


class _FlakyDepositor:
    """Échoue `failures` fois puis délègue au résultat fixe."""

    def __init__(self, failures: int) -> None:
        self._failures = failures
        self.calls = 0

    async def deposit(self, **_: Any) -> DepositResult:
        self.calls += 1
        if self.calls <= self._failures:
            raise ConnectionError("gateway timeout")
        return DepositResult(doc_id="stub-ok", slug="transcript-ok")


def _worker(pool: asyncpg.Pool, depositor: Any, minio: Any) -> DepositWorker:
    return DepositWorker(
        pool=pool, depositor=depositor, minio=minio, max_attempts=3, backoff_base_s=0.0
    )


async def test_tick_deposits_one_item(pool: asyncpg.Pool, tmp_path) -> None:
    seeded = await seed_request_with_item(pool, transcript_s3_key="t/vid-1.json")
    depositor = StubDepositor(output_dir=tmp_path)
    minio = FakeMinio({"t/vid-1.json": _PIVOT})

    processed = await _worker(pool, depositor, minio).tick()

    assert processed is True
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "deposited"
    assert row["docflow_doc_id"].startswith("stub-")
    assert row["docflow_slug"].startswith("transcript-")
    assert row["deposited_at"] is not None

    written = json.loads((tmp_path / f"{row['docflow_slug']}.json").read_text(encoding="utf-8"))
    assert written["transcript_text"] == (
        "Bonjour, dans cette vidéo…\non observe avant de questionner."
    )
    assert written["metadata"]["platform"] == "youtube"
    assert written["metadata"]["source_url"] == "https://youtube.com/@clea-ux"
    assert written["metadata"]["duration_s"] == 913
    assert written["metadata"]["request_key"] == seeded["request_key"]
    assert written["metadata"]["provider"] == "faster-whisper"


async def test_tick_returns_false_when_queue_empty(pool: asyncpg.Pool, tmp_path) -> None:
    worker = _worker(pool, StubDepositor(output_dir=tmp_path), FakeMinio({}))

    assert await worker.tick() is False


async def test_deposit_failure_marks_failed_with_code_and_keeps_transcript(
    pool: asyncpg.Pool,
) -> None:
    seeded = await seed_request_with_item(pool, transcript_s3_key="t/vid-1.json")
    depositor = _FlakyDepositor(failures=99)
    minio = FakeMinio({"t/vid-1.json": _PIVOT})

    await _worker(pool, depositor, minio).tick()

    assert depositor.calls == 3  # max_attempts, avec backoff entre chaque
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "failed"
    error = json.loads(row["error"])
    assert error["code"] == "DOCFLOW_DEPOSIT_FAILED"
    assert "gateway timeout" in error["message"]
    assert row["transcript_s3_key"] == "t/vid-1.json"


async def test_transient_failure_then_success(pool: asyncpg.Pool) -> None:
    seeded = await seed_request_with_item(pool, transcript_s3_key="t/vid-1.json")
    depositor = _FlakyDepositor(failures=1)
    minio = FakeMinio({"t/vid-1.json": _PIVOT})

    await _worker(pool, depositor, minio).tick()

    assert depositor.calls == 2
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "deposited"
    assert row["docflow_doc_id"] == "stub-ok"


async def test_missing_transcript_marks_failed(pool: asyncpg.Pool, tmp_path) -> None:
    seeded = await seed_request_with_item(pool, transcript_s3_key="t/absent.json")
    worker = _worker(pool, StubDepositor(output_dir=tmp_path), FakeMinio({}))

    await worker.tick()

    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "failed"
    assert json.loads(row["error"])["code"] == "DOCFLOW_DEPOSIT_FAILED"


async def test_recover_requeues_stale_depositing(pool: asyncpg.Pool, tmp_path) -> None:
    seeded = await seed_request_with_item(pool, item_status="depositing")
    worker = _worker(pool, StubDepositor(output_dir=tmp_path), FakeMinio({}))

    requeued = await worker.recover()

    assert requeued == 1
    row = await source_items_helper.get_by_id(seeded["item_id"], pool=pool)
    assert row["status"] == "transcribed"
