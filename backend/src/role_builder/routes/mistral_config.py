"""Endpoints REST pour la configuration Mistral d'un role_project.

Routes :
- GET  /api/role-projects/{project_id}/mistral-config
- PUT  /api/role-projects/{project_id}/mistral-config

Protégés par ``Depends(get_current_user)``.
Le secret Mistral réel vit dans le coffre ag.flow — Role Builder ne stocke
que la référence (``mistral_secret_ref``) pointant vers ce coffre.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_projects
from role_builder.schemas.mistral_config import (
    MistralConfigOut,
    SetMistralConfigRequest,
)

router = APIRouter()
log = structlog.get_logger(__name__)


def _status_for(secret_ref: str | None) -> str:
    if secret_ref is None or not secret_ref.strip():
        return "not-configured"
    # MVP : pas d'appel ag.flow `GET /api/admin/secrets`. Reporté Phase 2.
    # Tant qu'un secret_ref est fourni, on considère "configured".
    return "configured"


@router.get(
    "/role-projects/{project_id}/mistral-config",
    response_model=MistralConfigOut,
)
async def get_mistral_config_endpoint(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate
) -> MistralConfigOut:
    """Retourne la config Mistral du role_project (secret_ref + status déduit)."""
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")
    secret_ref = project.get("mistral_secret_ref")
    return MistralConfigOut(
        secret_ref=secret_ref,
        status=_status_for(secret_ref),  # type: ignore[arg-type]
    )


@router.put(
    "/role-projects/{project_id}/mistral-config",
    response_model=MistralConfigOut,
)
async def set_mistral_config_endpoint(
    project_id: UUID,
    request: SetMistralConfigRequest,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate
) -> MistralConfigOut:
    """Met à jour le secret_ref Mistral du role_project."""
    try:
        await role_projects.update_mistral_secret_ref(
            project_id,
            request.secret_ref,
            pool=db_pool.pool,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    log.info(
        "mistral_config.updated",
        project_id=str(project_id),
        configured=request.secret_ref is not None,
    )
    return MistralConfigOut(
        secret_ref=request.secret_ref,
        status=_status_for(request.secret_ref),  # type: ignore[arg-type]
    )
