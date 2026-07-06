"""Tests for db_helpers.source_items — bulk insert + filters + selection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.executemany_calls: list[tuple[str, list[tuple[Any, ...]]]] = []
        self.fetchval_return: Any = None
        self.fetch_return: list[Any] = []
        self.fetchrow_return: Any = None
        self.execute_return: str = "UPDATE 0"  # tag asyncpg par défaut

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def execute(self, query: str, *args: Any) -> str:
        self.calls.append(("execute", query, args))
        return self.execute_return

    async def executemany(self, query: str, args: list[tuple[Any, ...]]) -> None:
        self.executemany_calls.append((query, args))


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


async def test_insert_source_items_bulk_uses_executemany(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """insert_source_items_bulk uses executemany with ON CONFLICT DO NOTHING."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    tenant_id = uuid4()
    items = [
        {
            "id": "vid-1",
            "title": "T1",
            "duration_s": 100,
            "published_at": datetime(2024, 1, 1, tzinfo=UTC),
            "thumbnail_url": "http://x/1.jpg",
        },
        {
            "id": "vid-2",
            "title": "T2",
            "duration_s": 200,
            "published_at": None,
            "thumbnail_url": None,
        },
    ]

    inserted = await source_items.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=tenant_id, pool=stub_pool
    )

    assert inserted == 2
    assert len(stub_conn.executemany_calls) == 1
    query, batch = stub_conn.executemany_calls[0]
    assert "INSERT INTO source_items" in query
    assert "ON CONFLICT" in query
    assert len(batch) == 2
    # First row has source_id + tenant_id + platform_item_id 'vid-1'
    assert source_id in batch[0]
    assert tenant_id in batch[0]
    assert "vid-1" in batch[0]


async def test_insert_source_items_bulk_accepts_description_and_tags(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """description_excerpt/tags (list_discovered enrichi) sont optionnels, propagés si fournis."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    tenant_id = uuid4()
    items = [
        {
            "id": "vid-1",
            "title": "T1",
            "description_excerpt": "Dans cette vidéo…",
            "tags": ["ux", "interview"],
        },
        {"id": "vid-2", "title": "T2"},  # sans description/tags — doit rester optionnel
    ]

    await source_items.insert_source_items_bulk(
        items, source_id=source_id, tenant_id=tenant_id, pool=stub_pool
    )

    _, batch = stub_conn.executemany_calls[0]
    assert "Dans cette vidéo…" in batch[0]
    assert ["ux", "interview"] in batch[0]
    assert None in batch[1]  # description_excerpt absente -> None


async def test_update_source_item_status_executes_update(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """update_source_item_status updates by (source_id, platform_item_id)."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    await source_items.update_source_item_status(
        source_id,
        "vid-1",
        "audio_ready",
        audio_s3_key="bucket/path.mp3",
        pool=stub_pool,
    )

    assert len(stub_conn.calls) == 1
    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE source_items" in query
    assert "audio_ready" in args
    assert "bucket/path.mp3" in args
    assert source_id in args
    assert "vid-1" in args


async def test_list_items_by_source_applies_filters(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_items_by_source produces a WHERE with the filters supplied."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    stub_conn.fetch_return = [{"id": uuid4()}]
    since = datetime(2024, 1, 1, tzinfo=UTC)

    rows = await source_items.list_items_by_source(
        source_id,
        min_duration_s=120,
        since_date=since,
        status="audio_ready",
        selected=True,
        limit=10,
        offset=20,
        pool=stub_pool,
    )

    assert rows == [{"id": rows[0]["id"]}]
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM source_items" in query
    assert "duration_s" in query
    assert "published_at" in query
    assert "status" in query
    assert "selected" in query
    assert "LIMIT" in query
    assert "OFFSET" in query
    assert source_id in args
    assert 120 in args
    assert since in args
    assert "audio_ready" in args
    assert True in args
    assert 10 in args
    assert 20 in args


async def test_list_items_by_source_applies_extended_filters(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """max_duration_s / until_date / title_contains — filtres de la sélection auto (§2.1)."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    stub_conn.fetch_return = [{"id": uuid4()}]
    until = datetime(2024, 6, 1, tzinfo=UTC)

    await source_items.list_items_by_source(
        source_id,
        max_duration_s=1800,
        until_date=until,
        title_contains="UX",
        limit=10,
        offset=0,
        pool=stub_pool,
    )

    _, query, args = stub_conn.calls[0]
    assert "duration_s <=" in query
    assert "published_at <=" in query
    assert "title ILIKE" in query
    assert source_id in args
    assert 1800 in args
    assert until in args
    assert "%UX%" in args


async def test_count_by_status_groups_status_and_selected(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """count_by_status — support de request_status (counts agrégés, §2.3)."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    stub_conn.fetch_return = [
        {"status": "pending_download", "selected": True, "n": 3},
        {"status": "deposited", "selected": True, "n": 2},
    ]

    rows = await source_items.count_by_status(source_id, pool=stub_pool)

    assert rows == stub_conn.fetch_return
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "GROUP BY status, selected" in query
    assert source_id in args


async def test_reset_for_retry_clears_error_and_sets_pending(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """reset_for_retry — roles__retry_failed remet l'item à zéro (efface l'erreur)."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    await source_items.reset_for_retry(source_id, "vid-1", pool=stub_pool)

    method, query, args = stub_conn.calls[0]
    assert method == "execute"
    assert "UPDATE source_items" in query
    assert "pending_download" in query
    assert "error = NULL" in query
    assert source_id in args
    assert "vid-1" in args


async def test_select_items_marks_listed_and_optional_deselect(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """select_items marks the listed ids as selected; deselect_others toggles others off."""
    from role_builder.db_helpers import source_items

    source_id = uuid4()
    item_ids = [uuid4(), uuid4()]
    stub_conn.execute_return = "UPDATE 2"  # 2 lignes réellement sélectionnées

    count = await source_items.select_items(
        source_id, item_ids, deselect_others=True, pool=stub_pool
    )

    assert count == 2
    # Two SQL statements: deselect-others UPDATE + select-listed UPDATE
    assert len(stub_conn.calls) == 2
    methods = [c[0] for c in stub_conn.calls]
    queries = [c[1] for c in stub_conn.calls]
    # One UPDATE deselects (= false WHERE NOT id = ANY)
    assert any("selected = false" in q and "NOT" in q.upper() for q in queries), (
        f"missing deselect query: {queries}"
    )
    # One UPDATE marks selected
    assert any("selected = true" in q for q in queries)
    assert "execute" in methods or "fetchval" in methods
