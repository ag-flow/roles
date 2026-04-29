"""Routes Sprint 8 — GitHub publish (repos + config + publish + history).

Endpoints :
- GET    /api/github/repos
- GET    /api/role-projects/{id}/publication-config
- PUT    /api/role-projects/{id}/publication-config
- POST   /api/role-projects/{id}/publish-to-github         (T9)
- DELETE /api/role-projects/{id}/github-publication        (T9)
- GET    /api/role-projects/{id}/publications              (T9)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import (
    github_integrations,
    role_publication_config,
)
from role_builder.schemas.github import (
    GithubRepo,
    PublicationConfigOut,
    PublicationConfigRequest,
)
from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.openbao_client import OpenBaoClient

router = APIRouter()
log = structlog.get_logger(__name__)


def _bad_gateway(exc: httpx.HTTPStatusError) -> HTTPException:
    status_code = exc.response.status_code if exc.response is not None else None
    return HTTPException(
        status_code=502,
        detail=f"GitHub returned HTTP {status_code}: {exc}",
    )


@router.get("/github/repos", response_model=list[GithubRepo])
async def list_repos(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> list[GithubRepo]:
    integration = await github_integrations.get_by_user_id(
        user.user_id,
        pool=db_pool.pool,
    )
    if integration is None:
        raise HTTPException(status_code=400, detail="GitHub not connected")

    openbao = OpenBaoClient()
    try:
        token_data = await openbao.get(str(integration["openbao_path"]))
    finally:
        await openbao.aclose()

    access_token = (
        str(token_data["access_token"])
        if token_data and "access_token" in token_data
        else ""
    )
    if not access_token:
        raise HTTPException(
            status_code=502,
            detail="GitHub token missing in OpenBao",
        )

    api = GitHubApiClient(access_token=access_token)
    try:
        repos = await api.list_repos()
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    return [
        GithubRepo(
            full_name=str(r["full_name"]),
            private=bool(r["private"]),
            default_branch=str(r["default_branch"]),
            html_url=str(r["html_url"]),
        )
        for r in repos
    ]


@router.get(
    "/role-projects/{project_id}/publication-config",
    response_model=PublicationConfigOut,
)
async def get_publication_config(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> PublicationConfigOut:
    config = await role_publication_config.get_by_project_id(
        project_id,
        pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=404,
            detail="publication config not set for this project",
        )
    return PublicationConfigOut(**config)


@router.put("/role-projects/{project_id}/publication-config")
async def set_publication_config(
    project_id: UUID,
    body: PublicationConfigRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> dict[str, str]:
    await role_publication_config.upsert(
        role_project_id=project_id,
        repo_full_name=body.repo_full_name,
        target_subdirectory=body.target_subdirectory,
        branch=body.branch,
        commit_message_template=body.commit_message_template,
        license_choice=body.license_choice,
        pool=db_pool.pool,
    )
    log.info(
        "github.publication_config.saved",
        project_id=str(project_id),
        license=body.license_choice,
    )
    return {"status": "saved"}
