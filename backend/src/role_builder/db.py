"""Async PostgreSQL connection pool."""

from __future__ import annotations

import asyncpg

from role_builder.config import settings


class DBPool:
    """Wrapper around asyncpg pool tied to the app lifespan."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def connect(self) -> None:
        """Create the pool. Called once at app startup."""
        self._pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
        )

    async def disconnect(self) -> None:
        """Close the pool. Called once at app shutdown."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    @property
    def pool(self) -> asyncpg.Pool:
        """Return the active pool. Raises RuntimeError if disconnected."""
        if self._pool is None:
            raise RuntimeError("DB pool not connected")
        return self._pool


db_pool = DBPool()
