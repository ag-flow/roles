"""Endpoint REST pour la liste des role_projects du user courant.

Routes :
- GET /api/role-projects
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Depends

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_projects as role_projects_helper
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
