"""Endpoint REST de suivi des scraping_jobs.

GET /api/scraping-jobs?status=pending&limit=50 → liste des jobs (UI suivi).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import scraping_jobs as jobs_helper

router = APIRouter()


class ScrapingJobResponse(BaseModel):
    """Sortie API pour un scraping_job."""

    id: UUID
    source_id: UUID
    source_item_id: UUID | None = None
    tenant_id: UUID
    command: str
    status: str
    priority: int = 0
    attempts: int = 0
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


@router.get("/scraping-jobs", response_model=list[ScrapingJobResponse])
async def list_scraping_jobs(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ScrapingJobResponse]:
    """List scraping_jobs newest-first, optionally filtered by status."""
    pool = db_pool.pool
    rows = await jobs_helper.list_jobs(status=status, limit=limit, pool=pool)
    return [ScrapingJobResponse(**_pick(r)) for r in rows]


def _pick(row: dict[str, Any]) -> dict[str, Any]:
    """Subset row → ScrapingJobResponse fields."""
    keys = (
        "id",
        "source_id",
        "source_item_id",
        "tenant_id",
        "command",
        "status",
        "priority",
        "attempts",
        "error",
        "created_at",
        "started_at",
        "completed_at",
    )
    return {k: row.get(k) for k in keys}
