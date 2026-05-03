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
from pydantic import BaseModel

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import (
    github_integrations,
    role_documents,
    role_projects,
    role_publication_config,
    role_publications,
)
from role_builder.schemas.github import (
    GithubRepo,
    PublicationConfigOut,
    PublicationConfigRequest,
    PublicationOut,
    PublishResponse,
)
from role_builder.services.github_publish import publisher as gh_publisher
from role_builder.services.github_publish.api_client import GitHubApiClient
from role_builder.services.user_vault import get_service as _get_vault_service


class PublishRequest(BaseModel):
    """Phase 2 D : permet de cibler une intégration GitHub spécifique.

    Si ``integration_id`` est None, on utilise la primary (la plus récente).
    """

    integration_id: UUID | None = None


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
    integration_id: UUID | None = None,
) -> list[GithubRepo]:
    """Liste les repos. ``integration_id`` cible une intégration spécifique."""
    api, _login = await _api_for_user(user, integration_id=integration_id)
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


# ---------------------------------------------------------------------------
# Publish / Unpublish / History (T9)
# ---------------------------------------------------------------------------


async def _api_for_user(
    user: CurrentUser, *, integration_id: UUID | None = None,
) -> tuple[GitHubApiClient, str]:
    """Helper : récupère le token via Harpocrate et instancie un GitHubApiClient.

    Si ``integration_id`` est fourni, on cible cette intégration précise (et
    on vérifie qu'elle appartient bien au user). Sinon on prend la primary
    (la plus récente).

    Lève HTTPException 400 si non connecté, 403 si l'intégration appartient
    à un autre user, 404 si l'intégration n'existe pas, 502 si token manquant.
    """
    if integration_id is not None:
        integration = await github_integrations.get_by_id(
            integration_id, pool=db_pool.pool,
        )
        if integration is None:
            raise HTTPException(status_code=404, detail="integration not found")
        if integration["user_id"] != user.user_id:
            raise HTTPException(
                status_code=403, detail="not the integration owner",
            )
    else:
        integration = await github_integrations.get_by_user_id(
            user.user_id, pool=db_pool.pool,
        )
        if integration is None:
            raise HTTPException(status_code=400, detail="GitHub not connected")

    access_token = await _get_vault_service().read(str(integration["vault_secret_name"])) or ""
    if not access_token:
        raise HTTPException(
            status_code=502, detail="GitHub token missing in vault",
        )

    return (
        GitHubApiClient(access_token=access_token),
        str(integration["github_login"]),
    )


@router.post(
    "/role-projects/{project_id}/publish-to-github",
    response_model=PublishResponse,
)
async def publish_to_github(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    body: PublishRequest = PublishRequest(),  # noqa: B008
) -> PublishResponse:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")
    config = await role_publication_config.get_by_project_id(
        project_id, pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=400,
            detail="publication config not set for this project",
        )
    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )

    # Numéro de version du tag = (nombre de publications déjà faites) + 1
    existing = await role_publications.list_by_project(
        project_id, limit=1000, pool=db_pool.pool,
    )
    next_version = len(existing) + 1

    api, github_login = await _api_for_user(
        user, integration_id=body.integration_id,
    )
    try:
        result = await gh_publisher.push_publication(
            project=project,
            docs_by_section=docs_by_section,
            config=config,
            github_login=github_login,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            api=api,
            insert_publication=role_publications.insert,
            pool=db_pool.pool,
            tag_version_number=next_version,
        )
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    return PublishResponse(**result)


@router.delete("/role-projects/{project_id}/github-publication")
async def unpublish_from_github(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, int]:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")
    config = await role_publication_config.get_by_project_id(
        project_id, pool=db_pool.pool,
    )
    if config is None:
        raise HTTPException(
            status_code=400,
            detail="publication config not set for this project",
        )
    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )

    api, github_login = await _api_for_user(user)
    try:
        deleted = await gh_publisher.delete_publication(
            project=project,
            docs_by_section=docs_by_section,
            config=config,
            github_login=github_login,
            api=api,
        )
    except httpx.HTTPStatusError as exc:
        raise _bad_gateway(exc) from exc
    finally:
        await api.aclose()

    log.info(
        "github.unpublish.completed",
        project_id=str(project_id),
        deleted_files=deleted,
    )
    return {"deleted_files": deleted}


@router.get(
    "/role-projects/{project_id}/publications",
    response_model=list[PublicationOut],
)
async def list_publications(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> list[PublicationOut]:
    rows = await role_publications.list_by_project(
        project_id, pool=db_pool.pool,
    )
    return [PublicationOut(**r) for r in rows]
