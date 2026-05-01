"""Tests TDD pour db_helpers.corpus_stats."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


class _StubRow(dict):  # type: ignore[type-arg]
    pass


class _StubConn:
    def __init__(self, row: Any) -> None:
        self._row = row
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append((query, args))
        return self._row


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


@pytest.mark.asyncio
async def test_get_corpus_stats_returns_counts() -> None:
    from role_builder.db_helpers.corpus_stats import get_corpus_stats

    conn = _StubConn(_StubRow(source_count=12, chunk_count=530))
    pool = _StubPool(conn)
    project_id = uuid4()

    stats = await get_corpus_stats(project_id, pool=pool)

    assert stats == {"source_count": 12, "chunk_count": 530}
    # Vérifie que la query a bien reçu le project_id en arg
    assert conn.calls[0][1] == (project_id,)


@pytest.mark.asyncio
async def test_get_corpus_stats_handles_zero_rows() -> None:
    from role_builder.db_helpers.corpus_stats import get_corpus_stats

    conn = _StubConn(_StubRow(source_count=0, chunk_count=0))
    pool = _StubPool(conn)

    stats = await get_corpus_stats(uuid4(), pool=pool)
    assert stats == {"source_count": 0, "chunk_count": 0}


@pytest.mark.asyncio
async def test_get_corpus_stats_returns_zeros_when_row_is_none() -> None:
    """Cas dégénéré (pool/connection drop) : retourne 0/0 plutôt que crasher."""
    from role_builder.db_helpers.corpus_stats import get_corpus_stats

    conn = _StubConn(None)
    pool = _StubPool(conn)

    stats = await get_corpus_stats(uuid4(), pool=pool)
    assert stats == {"source_count": 0, "chunk_count": 0}
