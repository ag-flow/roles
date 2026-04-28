"""Tests for db_helpers.corpus_chunks — bulk insert + semantic_search pgvector."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []
        self.executemany_calls: list[tuple[str, list[Any]]] = []

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

    async def executemany(self, query: str, rows: list[Any]) -> None:
        self.executemany_calls.append((query, rows))


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


async def test_insert_chunks_bulk_inserts_all_rows(stub_conn: _StubConn, stub_pool: Any) -> None:
    """insert_chunks_bulk fait un executemany avec un row par chunk."""
    from role_builder.db_helpers import corpus_chunks

    item_id = uuid4()
    project_id = uuid4()
    tenant_id = uuid4()
    chunks = [
        {
            "chunk_index": 0,
            "start_s": 0.0,
            "end_s": 10.0,
            "text": "Hello",
            "embedding": [0.1] * 1024,
        },
        {
            "chunk_index": 1,
            "start_s": 10.0,
            "end_s": 20.0,
            "text": "World",
            "embedding": [0.2] * 1024,
        },
    ]

    n = await corpus_chunks.insert_chunks_bulk(
        chunks,
        source_item_id=item_id,
        role_project_id=project_id,
        tenant_id=tenant_id,
        pool=stub_pool,
    )

    assert n == 2
    assert len(stub_conn.executemany_calls) == 1
    query, rows = stub_conn.executemany_calls[0]
    assert "INSERT INTO corpus_chunks" in query
    assert "embedding" in query
    assert len(rows) == 2
    # Première ligne : ids + chunk_index 0 + payload
    first = rows[0]
    assert item_id in first
    assert project_id in first
    assert tenant_id in first
    assert 0 in first
    assert "Hello" in first


async def test_insert_chunks_bulk_empty_returns_zero(stub_conn: _StubConn, stub_pool: Any) -> None:
    """Liste vide → pas d'appel SQL, retourne 0."""
    from role_builder.db_helpers import corpus_chunks

    n = await corpus_chunks.insert_chunks_bulk(
        [],
        source_item_id=uuid4(),
        role_project_id=uuid4(),
        tenant_id=uuid4(),
        pool=stub_pool,
    )
    assert n == 0
    assert stub_conn.executemany_calls == []
    assert stub_conn.calls == []


async def test_semantic_search_orders_by_cosine_distance(
    stub_conn: _StubConn, stub_pool: Any
) -> None:
    """semantic_search emet ORDER BY embedding <=> $X et calcule similarity."""
    from role_builder.db_helpers import corpus_chunks

    project_id = uuid4()
    chunk1_id = uuid4()
    chunk2_id = uuid4()
    item_id = uuid4()
    # Le helper retourne aussi la 'distance' (cosine), qu'on transforme en similarity.
    stub_conn.fetch_return = [
        {
            "chunk_id": chunk1_id,
            "source_item_id": item_id,
            "text": "best match",
            "start_s": 0.0,
            "end_s": 10.0,
            "distance": 0.1,
        },
        {
            "chunk_id": chunk2_id,
            "source_item_id": item_id,
            "text": "lower match",
            "start_s": 10.0,
            "end_s": 20.0,
            "distance": 0.5,
        },
    ]

    query_embedding = [0.1] * 1024
    results = await corpus_chunks.semantic_search(
        role_project_id=project_id,
        query_embedding=query_embedding,
        limit=5,
        min_similarity=0.0,
        pool=stub_pool,
    )

    assert len(results) == 2
    # Similarity = 1 - distance ; chunk1 doit être avant chunk2.
    assert results[0]["chunk_id"] == chunk1_id
    assert results[0]["similarity"] == pytest.approx(0.9)
    assert results[1]["similarity"] == pytest.approx(0.5)

    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM corpus_chunks" in query
    assert "<=>" in query
    assert "ORDER BY" in query
    assert project_id in args
    assert 5 in args


async def test_semantic_search_filters_min_similarity(stub_conn: _StubConn, stub_pool: Any) -> None:
    """min_similarity=0.7 filtre côté Python (les rows < seuil sont droppées)."""
    from role_builder.db_helpers import corpus_chunks

    stub_conn.fetch_return = [
        {
            "chunk_id": uuid4(),
            "source_item_id": uuid4(),
            "text": "high",
            "start_s": 0.0,
            "end_s": 10.0,
            "distance": 0.1,  # similarity 0.9
        },
        {
            "chunk_id": uuid4(),
            "source_item_id": uuid4(),
            "text": "low",
            "start_s": 0.0,
            "end_s": 10.0,
            "distance": 0.6,  # similarity 0.4
        },
    ]
    results = await corpus_chunks.semantic_search(
        role_project_id=uuid4(),
        query_embedding=[0.0] * 1024,
        limit=10,
        min_similarity=0.7,
        pool=stub_pool,
    )
    assert len(results) == 1
    assert results[0]["text"] == "high"


async def test_list_by_item_filters_by_source_item(stub_conn: _StubConn, stub_pool: Any) -> None:
    """list_by_item filtre source_item_id + LIMIT/OFFSET."""
    from role_builder.db_helpers import corpus_chunks

    item_id = uuid4()
    rows = [{"id": uuid4(), "text": "a"}, {"id": uuid4(), "text": "b"}]
    stub_conn.fetch_return = rows
    result = await corpus_chunks.list_by_item(item_id, limit=10, offset=5, pool=stub_pool)
    assert result == rows
    method, query, args = stub_conn.calls[0]
    assert method == "fetch"
    assert "FROM corpus_chunks" in query
    assert "source_item_id = $1" in query
    assert item_id in args
    assert 10 in args
    assert 5 in args


async def test_count_by_project(stub_conn: _StubConn, stub_pool: Any) -> None:
    """count_by_project retourne le COUNT pour un role_project_id."""
    from role_builder.db_helpers import corpus_chunks

    project_id = uuid4()
    stub_conn.fetchval_return = 42
    n = await corpus_chunks.count_by_project(project_id, pool=stub_pool)
    assert n == 42
    method, query, args = stub_conn.calls[0]
    assert method == "fetchval"
    assert "count(" in query.lower()
    assert "FROM corpus_chunks" in query
    assert "role_project_id = $1" in query
    assert project_id in args
