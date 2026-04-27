"""Health-check endpoint."""
from __future__ import annotations

from fastapi import APIRouter

from role_builder.db import db_pool

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, object]:
    """Return ok with db=true|false. Never 5xx — DB outage shouldn't crash the probe."""
    try:
        async with db_pool.pool.acquire() as conn:
            db_ok = await conn.fetchval("SELECT 1") == 1
    except Exception:
        db_ok = False
    return {"status": "ok", "db": db_ok}
