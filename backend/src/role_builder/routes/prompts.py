"""Endpoints REST pour la bibliothèque de prompts versionnés.

Routes :
- GET  /api/prompts
- GET  /api/prompts/{prompt_id}/versions
- POST /api/prompts/{prompt_id}/versions
- PUT  /api/prompts/{prompt_id}/system-default/{version_id}

Tous protégés par ``Depends(get_current_user)`` (bypass via
``settings.disable_auth=True`` en tests/dev).
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException, status

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import prompts as prompts_helper
from role_builder.schemas.prompts import CreateVersionRequest, PromptOut, PromptVersionOut

log = structlog.get_logger(__name__)

router = APIRouter()


@router.get("", response_model=list[PromptOut])
async def list_prompts(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PromptOut]:
    """Retourne tous les prompts de la bibliothèque."""
    pool = db_pool.pool
    rows = await prompts_helper.list_prompts(pool=pool)
    return [PromptOut(**r) for r in rows]


@router.get("/{prompt_id}/versions", response_model=list[PromptVersionOut])
async def list_prompt_versions(
    prompt_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[PromptVersionOut]:
    """Retourne toutes les versions d'un prompt, triées par version_number DESC."""
    pool = db_pool.pool
    rows = await prompts_helper.list_versions(prompt_id, pool=pool)
    return [PromptVersionOut(**r) for r in rows]


@router.post(
    "/{prompt_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=PromptVersionOut,
)
async def create_prompt_version(
    prompt_id: UUID,
    body: CreateVersionRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> PromptVersionOut:
    """Crée une nouvelle version utilisateur pour un prompt.

    - is_system_default = False (version user)
    - version_number = max(existantes) + 1
    - created_by = user.user_id si disponible
    """
    pool = db_pool.pool
    existing = await prompts_helper.list_versions(prompt_id, pool=pool)
    next_version = (max((v["version_number"] for v in existing), default=0)) + 1

    new_id = await prompts_helper.insert_prompt_version(
        prompt_id=prompt_id,
        version_number=next_version,
        template=body.template,
        is_system_default=False,
        created_by=user.user_id,
        pool=pool,
    )

    row = await prompts_helper.get_version_by_id(new_id, pool=pool)
    if row is None:  # pragma: no cover — défensif
        raise HTTPException(status_code=500, detail="version disparue après insert")

    log.info(
        "api.prompts.version_created",
        prompt_id=str(prompt_id),
        version_number=next_version,
        version_id=str(new_id),
    )
    return PromptVersionOut(**row)


@router.put(
    "/{prompt_id}/system-default/{version_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def set_system_default(
    prompt_id: UUID,
    version_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> None:
    """Promeut une version comme system_default pour un prompt.

    Désactive toutes les autres versions, puis active version_id.
    """
    pool = db_pool.pool
    try:
        await prompts_helper.set_system_default(prompt_id, version_id, pool=pool)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="version not found for this prompt") from exc
    log.info(
        "api.prompts.system_default_updated",
        prompt_id=str(prompt_id),
        version_id=str(version_id),
    )
