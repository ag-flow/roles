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
from role_builder.db_helpers import credentials as credentials_helper
from role_builder.db_helpers import role_projects as role_projects_helper
from role_builder.db_helpers import scraping_jobs as jobs_helper
from role_builder.db_helpers import source_items as items_helper
from role_builder.db_helpers import sources as sources_helper
from role_builder.schemas.items import SelectItemsRequest, SourceItemResponse
from role_builder.schemas.sources import CreateSourceRequest, SourceResponse

log = structlog.get_logger(__name__)

router = APIRouter()


async def _require_owned_source(
    source_id: UUID, user: CurrentUser, pool: Any
) -> dict[str, Any]:
    """Charge une source et vérifie qu'elle appartient à l'appelant.

    Source rattachée à un role_project : le projet doit appartenir au user
    (sinon 404 — pas d'accès aux items/cookies d'autrui). Source V2 (façade
    MCP, `role_project_id` NULL) : pas de propriétaire par user, scope tenant
    (MVP mono-tenant) en attendant l'identité pilote.
    """
    source = await sources_helper.get_source(source_id, pool=pool)
    if source is None:
        raise HTTPException(status_code=404, detail="source not found")
    role_project_id = source.get("role_project_id")
    if role_project_id is not None:
        owner_id = await role_projects_helper.get_user_id_for_project(role_project_id, pool=pool)
        if owner_id != user.user_id:
            raise HTTPException(status_code=404, detail="source not found")
    return source


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
    # Vérifie la propriété : projet appartenant au user, et credential (si
    # fourni) appartenant au user — sinon 404. Sans ça, un UUID inexistant
    # levait une FK 500, et un credentials_id d'autrui faisait scraper avec
    # les cookies de la victime (BUG-31).
    owner_id = await role_projects_helper.get_user_id_for_project(role_project_id, pool=pool)
    if owner_id != user.user_id:
        raise HTTPException(status_code=404, detail="role project not found")
    if body.credentials_id is not None:
        cred = await credentials_helper.get_credential(
            body.credentials_id, user_id=user.user_id, pool=pool
        )
        if cred is None:
            raise HTTPException(status_code=404, detail="credential not found")
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
    source = await _require_owned_source(source_id, user, pool)

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
    await _require_owned_source(source_id, user, pool)
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
    """Mark items as selected, then create one download job per selected item.

    Valide que les item_ids appartiennent à la source (rejet 400 sinon : pas de
    job hors périmètre, pas de FK 500) et reste idempotent (pas de doublon de
    download pour un item déjà en vol).
    """
    pool = db_pool.pool
    source = await _require_owned_source(source_id, user, pool)

    requested = list(dict.fromkeys(body.item_ids))  # dédoublonne en préservant l'ordre
    items = await items_helper.list_items_by_ids(source_id, requested, pool=pool)
    valid_ids = {item["id"] for item in items}
    unknown = [str(i) for i in requested if i not in valid_ids]
    if unknown:
        raise HTTPException(
            status_code=400, detail={"error": "unknown_items", "item_ids": unknown}
        )

    selected_count = await items_helper.select_items(
        source_id, requested, deselect_others=body.deselect_others, pool=pool
    )

    jobs_created = 0
    for item in items:
        if await jobs_helper.get_active_job_for_item(item["id"], "download", pool=pool):
            continue  # download déjà en vol pour cet item (idempotence)
        await jobs_helper.insert_job(
            source_id=source_id,
            source_item_id=item["id"],
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
