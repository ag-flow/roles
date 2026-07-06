"""Tests pour worker.db — helpers asyncpg du worker de transcription."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest


class _StubTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.transaction_count = 0

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> None:
        self.calls.append(("execute", query, args))

    def transaction(self) -> _StubTransaction:
        self.transaction_count += 1
        return _StubTransaction()


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


async def test_claim_next_job_returns_none_when_no_pending(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_job retourne None si aucun job pending pour ce pool."""
    from worker import db

    stub_conn.fetchrow_return = None
    result = await db.claim_next_job("shared_default", "worker-1", pool=stub_pool)
    assert result is None
    # Transaction ouverte (atomicité SELECT FOR UPDATE / UPDATE)
    assert stub_conn.transaction_count == 1
    methods = [c[0] for c in stub_conn.calls]
    assert "fetchrow" in methods
    assert "execute" not in methods


async def test_claim_next_job_select_for_update_skip_locked_then_update(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """claim_next_job exécute SELECT FOR UPDATE SKIP LOCKED puis UPDATE status='claimed'."""
    from worker import db

    job_id = uuid4()
    job_row = {
        "id": job_id,
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/x.mp3",
        "language": "fr",
        "worker_pool_id": "shared_default",
        "attempts": 0,
    }
    stub_conn.fetchrow_return = job_row

    result = await db.claim_next_job("shared_default", "worker-1", pool=stub_pool)

    assert result == job_row
    methods = [c[0] for c in stub_conn.calls]
    assert methods == ["fetchrow", "execute"]
    # SELECT FOR UPDATE SKIP LOCKED restreint au pool, status pending
    select_query, select_args = stub_conn.calls[0][1], stub_conn.calls[0][2]
    assert "FROM transcription_jobs" in select_query
    assert "FOR UPDATE" in select_query
    assert "SKIP LOCKED" in select_query
    assert "pending" in select_query
    assert "shared_default" in select_args
    # UPDATE → status='claimed', worker assigné, attempts incremente
    update_query, update_args = stub_conn.calls[1][1], stub_conn.calls[1][2]
    assert "UPDATE transcription_jobs" in update_query
    assert "claimed" in update_query
    assert "worker-1" in update_args
    assert job_id in update_args


async def test_mark_job_done_updates_status_and_costs(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """mark_job_done écrit provider_used + costs + result_s3_key."""
    from worker import db

    job_id = uuid4()
    await db.mark_job_done(
        job_id,
        provider_used="openai-whisper",
        cost_estimate_usd=0.0123,
        cost_actual_usd=None,
        result_s3_key="corpus-transcripts/x.json",
        pool=stub_pool,
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE transcription_jobs" in query
    assert "done" in query
    assert "openai-whisper" in args
    assert 0.0123 in args
    assert None in args  # cost_actual_usd
    assert "corpus-transcripts/x.json" in args
    assert job_id in args


async def test_mark_job_failed_appends_error_history_and_increments(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """mark_job_failed append à error_history (jsonb) et set status='failed' + attempts+1."""
    from worker import db

    job_id = uuid4()
    entry = {
        "at": "2026-04-26T10:00:00+00:00",
        "category": "exhausted",
        "message": "insufficient_quota",
    }
    await db.mark_job_failed(
        job_id,
        error="insufficient_quota",
        error_history_entry=entry,
        pool=stub_pool,
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE transcription_jobs" in query
    assert "failed" in query
    # Append jsonb : error_history = COALESCE(error_history, '[]'::jsonb) || $X::jsonb
    assert "error_history" in query
    assert "jsonb" in query
    # attempts = attempts + 1
    assert "attempts" in query and "+ 1" in query
    assert "insufficient_quota" in args
    # entry est passé sérialisé en JSON string ou tel quel
    # selon impl ; l'entry doit être présent dans args (string JSON ou dict)
    found = any(
        (isinstance(a, str) and "exhausted" in a) or a == entry
        for a in args
    )
    assert found, f"entry should be in args: {args}"
    assert job_id in args


async def test_update_source_item_to_transcribed_writes_status_and_key(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_source_item_to_transcribed écrit status='transcribed' + transcript_s3_key."""
    from worker import db

    item_id = uuid4()
    await db.update_source_item_to_transcribed(
        item_id, "corpus-transcripts/x.json", pool=stub_pool
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE source_items" in query
    assert "transcribed" in query
    assert "transcript_s3_key" in query
    assert "corpus-transcripts/x.json" in args
    assert item_id in args


async def test_reassign_pending_to_shared_returns_count(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """reassign_pending_to_shared bascule les jobs pending d'un user_pool vers shared."""
    from worker import db

    # asyncpg execute renvoie un command tag genre "UPDATE 3" ; on stub sur fetchval
    # pour avoir un compteur exact via UPDATE ... RETURNING.
    stub_conn.fetchval_return = 3
    count = await db.reassign_pending_to_shared("user_abc", pool=stub_pool)
    assert count == 3
    method, query, args = stub_conn.calls[0]
    # Implémentation : UPDATE ... RETURNING count via WITH/aggregate ou simple fetchval
    assert "UPDATE transcription_jobs" in query
    assert "shared_default" in query
    assert "pending" in query
    assert "user_abc" in args


async def test_register_worker_inserts_row_with_provider_and_status(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """register_worker fait un INSERT (idempotent) sur transcription_workers."""
    from worker import db

    await db.register_worker(
        "rb-worker-shared-1",
        "shared_default",
        "faster-whisper",
        status="idle",
        host="pve2",
        pool=stub_pool,
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "INSERT INTO transcription_workers" in query
    # idempotent via ON CONFLICT pour pouvoir restart sans purger la table
    assert "ON CONFLICT" in query
    assert "rb-worker-shared-1" in args
    assert "shared_default" in args
    assert "faster-whisper" in args
    assert "idle" in args
    assert "pve2" in args


async def test_update_worker_status_writes_status_and_optional_timestamps(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_worker_status met le status + last_activity_at / stopped_at quand fournis."""
    from worker import db

    now = datetime.now(UTC)
    await db.update_worker_status(
        "rb-worker-shared-1",
        "idle",
        last_activity_at=now,
        pool=stub_pool,
    )
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE transcription_workers" in query
    assert "last_activity_at" in query
    assert "rb-worker-shared-1" in args
    assert now in args
    assert "idle" in args

    # Sans last_activity_at ni stopped_at : seul le status est mis à jour
    stub_conn.calls.clear()
    await db.update_worker_status("rb-worker-shared-1", "busy", pool=stub_pool)
    _, q2, a2 = stub_conn.calls[0]
    assert "UPDATE transcription_workers" in q2
    assert "busy" in a2
    # last_activity_at n'apparaît pas dans la SET clause
    assert "last_activity_at" not in q2
    assert "stopped_at" not in q2

    # Avec stopped_at
    stub_conn.calls.clear()
    await db.update_worker_status(
        "rb-worker-shared-1", "stopped", stopped_at=now, pool=stub_pool
    )
    _, q3, a3 = stub_conn.calls[0]
    assert "stopped_at" in q3
    assert "stopped" in a3
    assert now in a3
