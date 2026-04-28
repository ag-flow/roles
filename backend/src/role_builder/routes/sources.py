"""Endpoints REST sources + source_items.

Routes :
- POST /api/role-projects/{role_project_id}/sources
- POST /api/sources/{source_id}/discover
- GET  /api/sources/{source_id}/items
- POST /api/sources/{source_id}/items/select

Authentification : Keycloak Bearer (Phase A). Le `tenant_id` provient du
`CurrentUser` (constante `TENANT_ID_DEFAULT` MVP, multi-tenant Phase 2).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import scraping_jobs as jobs_helper
from role_builder.db_helpers import source_items as items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.schemas.items import SelectItemsRequest, SourceItemResponse
from role_builder.schemas.sources import CreateSourceRequest, SourceResponse

log = structlog.get_logger(__name__)

router = APIRouter()


@router.post(
    "/role-projects/{role_project_id}/sources",
    status_code=status.HTTP_201_CREATED,
    response_model=SourceResponse,
)
async def create_source(
    role_project_id: UUID,
    body: CreateSourceRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> SourceResponse:
    """Create a new source row, return it as SourceResponse."""
    pool = db_pool.pool
    new_id = await sources_helper.insert_source(
        role_project_id=role_project_id,
        tenant_id=user.tenant_id,
        platform=body.platform,
        source_type=body.source_type,
        url=str(body.url),
        credentials_id=body.credentials_id,
        pool=pool,
    )
    row = await sources_helper.get_source(new_id, pool=pool)
    if row is None:  # pragma: no cover — defensive
        raise HTTPException(status_code=500, detail="source disappeared after insert")
    return SourceResponse(**row)


@router.post(
    "/sources/{source_id}/discover",
    status_code=status.HTTP_202_ACCEPTED,
)
async def discover_source(
    source_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str]:
    """Create a scraping_jobs row with command='discover' for this source."""
    pool = db_pool.pool
    source = await sources_helper.get_source(source_id, pool=pool)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    job_id = await jobs_helper.insert_job(
        source_id=source_id,
        source_item_id=None,
        tenant_id=user.tenant_id,
        command="discover",
        credentials_id=source.get("credentials_id"),
        priority=0,
        pool=pool,
    )
    log.info("api.discover_job_created", source_id=str(source_id), job_id=str(job_id))
    return {"job_id": str(job_id)}


@router.get(
    "/sources/{source_id}/items",
    response_model=list[SourceItemResponse],
)
async def list_source_items(
    source_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    min_duration_s: int | None = Query(default=None, ge=0),
    since_date: datetime | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    selected: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SourceItemResponse]:
    """Paginated list of items for a source, with optional filters."""
    pool = db_pool.pool
    rows = await items_helper.list_items_by_source(
        source_id,
        min_duration_s=min_duration_s,
        since_date=since_date,
        status=status_filter,
        selected=selected,
        limit=limit,
        offset=offset,
        pool=pool,
    )
    return [SourceItemResponse(**_pick_item_fields(r)) for r in rows]


@router.post("/sources/{source_id}/items/select")
async def select_items(
    source_id: UUID,
    body: SelectItemsRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, int]:
    """Mark items as selected, then create one download job per selected item."""
    pool = db_pool.pool
    source = await sources_helper.get_source(source_id, pool=pool)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")

    selected_count = await items_helper.select_items(
        source_id,
        body.item_ids,
        deselect_others=body.deselect_others,
        pool=pool,
    )

    jobs_created = 0
    for item_id in body.item_ids:
        await jobs_helper.insert_job(
            source_id=source_id,
            source_item_id=item_id,
            tenant_id=user.tenant_id,
            command="download",
            credentials_id=source.get("credentials_id"),
            priority=0,
            pool=pool,
        )
        jobs_created += 1

    log.info(
        "api.select_items",
        source_id=str(source_id),
        selected_count=selected_count,
        jobs_created=jobs_created,
    )
    return {"selected_count": selected_count, "jobs_created": jobs_created}


def _pick_item_fields(row: dict[str, Any]) -> dict[str, Any]:
    """Subset row → SourceItemResponse fields (schema is strict on extras)."""
    keys = (
        "id",
        "platform_item_id",
        "title",
        "duration_s",
        "published_at",
        "thumbnail_url",
        "status",
        "selected",
        "audio_s3_key",
        "error",
    )
    return {k: row.get(k) for k in keys}
