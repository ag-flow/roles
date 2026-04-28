"""Routes Sprint 7 — export ag.flow.

Conventions :
- Toutes les routes protégées par `Depends(get_current_user)`.
- Erreurs métier mappées vers HTTPException (400 si validation, 404 si introuvable).
- L'erreur HTTP côté ag.flow (httpx.HTTPStatusError) est mappée vers 502 Bad Gateway.
"""

from __future__ import annotations

from uuid import UUID

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Response

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_documents, role_projects
from role_builder.schemas.agflow_export import (
    GeneratePromptsResponse,
    PreviewSection,
    PreviewSectionDoc,
    PreviewZipResponse,
    PushToAgflowRequest,
    PushToAgflowResponse,
)
from role_builder.services.agflow import push as agflow_push
from role_builder.services.agflow.api_client import get_agflow_admin_client
from role_builder.services.agflow.exporter import build_role_zip

router = APIRouter()
log = structlog.get_logger(__name__)


def _bad_gateway_from_httpx(exc: httpx.HTTPStatusError) -> HTTPException:
    """Map une HTTPStatusError d'ag.flow vers une HTTPException 502 lisible."""
    status = exc.response.status_code if exc.response else None
    return HTTPException(
        status_code=502,
        detail=f"ag.flow returned HTTP {status}: {exc}",
    )


@router.get(
    "/role-projects/{project_id}/preview-zip",
    response_model=PreviewZipResponse,
)
async def preview_zip_endpoint(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001 — auth gate
) -> PreviewZipResponse:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")

    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id,
        pool=db_pool.pool,
    )

    sections: list[PreviewSection] = []
    for section_name, docs in docs_by_section.items():
        sections.append(
            PreviewSection(
                name=section_name,
                documents=[
                    PreviewSectionDoc(
                        name=str(d["name"]),
                        size=len(str(d.get("content") or "")),
                    )
                    for d in docs
                ],
            )
        )

    missing = agflow_push.check_missing_pieces(project, docs_by_section)
    identity = project.get("identity") or ""

    return PreviewZipResponse(
        display_name=str(project["display_name"]),
        description=project.get("description"),
        identity_length=len(str(identity)),
        target_role_id=project.get("target_role_id"),
        sections=sections,
        ready_to_push=not missing,
        missing=missing,
    )


@router.post(
    "/role-projects/{project_id}/push-to-agflow",
    response_model=PushToAgflowResponse,
)
async def push_to_agflow_endpoint(
    project_id: UUID,
    request: PushToAgflowRequest,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> PushToAgflowResponse:
    try:
        result = await agflow_push.push_role_to_agflow(
            project_id,
            generate_prompts=request.generate_prompts,
            pool=db_pool.pool,
        )
    except RuntimeError as exc:
        msg = str(exc)
        if "not found" in msg:
            raise HTTPException(status_code=404, detail=msg) from exc
        raise HTTPException(status_code=400, detail=msg) from exc
    except httpx.HTTPStatusError as exc:
        log.exception("agflow.push.upstream_error", project_id=str(project_id))
        raise _bad_gateway_from_httpx(exc) from exc
    except httpx.HTTPError as exc:
        log.exception("agflow.push.transport_error", project_id=str(project_id))
        raise HTTPException(
            status_code=502,
            detail=f"ag.flow transport error: {exc}",
        ) from exc

    log.info(
        "agflow.push.completed", project_id=str(project_id), agflow_role_id=result["agflow_role_id"]
    )
    return PushToAgflowResponse(**result)


@router.post(
    "/role-projects/{project_id}/generate-prompts-on-agflow",
    response_model=GeneratePromptsResponse,
)
async def generate_prompts_endpoint(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> GeneratePromptsResponse:
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")

    target_role_id = project.get("target_role_id")
    if not target_role_id:
        raise HTTPException(
            status_code=400,
            detail="role not yet pushed to ag.flow (no target_role_id)",
        )

    client = get_agflow_admin_client()
    try:
        await client.generate_prompts(str(target_role_id))
    except httpx.HTTPStatusError as exc:
        log.exception("agflow.generate_prompts.upstream_error", project_id=str(project_id))
        raise _bad_gateway_from_httpx(exc) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"ag.flow transport error: {exc}",
        ) from exc

    log.info("agflow.generate_prompts.completed", project_id=str(project_id))
    return GeneratePromptsResponse(
        status="generated",
        target_role_id=str(target_role_id),
    )


@router.get(
    "/role-projects/{project_id}/download-zip",
    responses={200: {"content": {"application/zip": {}}}},
)
async def download_zip_endpoint(
    project_id: UUID,
    user: CurrentUser = Depends(get_current_user),  # noqa: ARG001
) -> Response:
    """Construit et retourne le ZIP sans le pousser (debug / archive locale)."""
    project = await role_projects.get_by_id(project_id, pool=db_pool.pool)
    if project is None:
        raise HTTPException(status_code=404, detail="role project not found")

    docs_by_section = await role_documents.list_current_by_project_grouped(
        project_id,
        pool=db_pool.pool,
    )
    missing = agflow_push.check_missing_pieces(project, docs_by_section)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"cannot build ZIP: missing pieces — {missing}",
        )

    try:
        build = build_role_zip(project, docs_by_section)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    filename = f"role-{project_id}.zip"
    return Response(
        content=build.zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
