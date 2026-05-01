"""Endpoints REST pour les role_projects.

Routes :
- GET   /api/role-projects                                       — liste
- PATCH /api/role-projects/{id}/global-directives                — édite
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_projects as role_projects_helper
from role_builder.db_helpers import runs as runs_helper
from role_builder.schemas.role_projects import RoleProjectOut

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get("/role-projects", response_model=list[RoleProjectOut])
async def list_role_projects_endpoint(
    user: CurrentUser = Depends(get_current_user),
) -> list[RoleProjectOut]:
    """Liste tous les role_projects appartenant au user courant."""
    rows = await role_projects_helper.list_for_user(user.user_id, pool=db_pool.pool)
    log.info("role_projects.listed", user_id=str(user.user_id), count=len(rows))
    return [RoleProjectOut(**r) for r in rows]


class GlobalDirectivesPatch(BaseModel):
    """Body pour PATCH global-directives."""

    global_directives: str | None = None


@router.patch(
    "/role-projects/{project_id}/global-directives",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def patch_global_directives(
    project_id: UUID,
    body: GlobalDirectivesPatch,
    user: CurrentUser = Depends(get_current_user),
) -> None:
    """Édite les directives globales et marque les runs existants obsolete.

    Les runs antérieurs deviennent obsolete (badge UI) car ils ont été
    générés avec des paramètres qui ne sont plus en vigueur. Pas de
    cascade vers les signals/clusters/documents — seul `runs.is_obsolete`
    est touché.
    """
    pool = db_pool.pool
    project = await role_projects_helper.get_by_id(project_id, pool=pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role_project not found")
    if project["user_id"] != user.user_id:
        raise HTTPException(status_code=403, detail="not the project owner")

    await role_projects_helper.update_global_directives(
        project_id, body.global_directives, pool=pool,
    )
    rowcount = await runs_helper.mark_obsolete_for_project(project_id, pool=pool)
    log.info(
        "role_projects.global_directives_updated",
        project_id=str(project_id),
        runs_marked_obsolete=rowcount,
    )
