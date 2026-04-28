"""Tests for the asyncpg pool wrapper."""

from __future__ import annotations

import pytest

from role_builder.db import DBPool


def test_db_pool_starts_disconnected() -> None:
    """A fresh DBPool has no active pool."""
    pool = DBPool()
    with pytest.raises(RuntimeError, match="not connected"):
        _ = pool.pool
