"""Health-check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from role_builder.db import db_pool

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, object]:
    """Return ok when the app and DB are reachable."""
    async with db_pool.pool.acquire() as conn:
        result = await conn.fetchval("SELECT 1")
    return {"status": "ok", "db": result == 1}
