"""Routes Sprint 7 Phase D — lecture / édition des role_documents.

Conventions :
- Toutes protégées par ``Depends(get_current_user)``.
- 404 si introuvable, 422 si Pydantic, 200 sinon.
- Le router est inclus dans main.py avec ``prefix="/api"``.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException

from role_builder.auth.dependencies import CurrentUser, get_current_user
from role_builder.db import db_pool
from role_builder.db_helpers import role_documents
from role_builder.schemas.role_documents import (
    LockResponse,
    RoleDocumentOut,
    RoleDocumentsBySection,
    RoleDocumentSummary,
    UpdateRoleDocumentRequest,
)

router = APIRouter()
log = structlog.get_logger(__name__)


@router.get(
    "/role-projects/{project_id}/role-documents",
    response_model=RoleDocumentsBySection,
)
async def list_grouped(
    project_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> RoleDocumentsBySection:
    grouped = await role_documents.list_current_by_project_grouped(
        project_id, pool=db_pool.pool,
    )
    sections: dict[str, list[RoleDocumentSummary]] = {}
    for section_name, docs in grouped.items():
        sections[section_name] = [
            RoleDocumentSummary(
                id=d["id"],
                section=str(d["section"]),
                name=str(d["name"]),
                version=int(d["version"]),
                is_current=bool(d["is_current"]),
                locked=bool(d["locked"]),
                updated_at=d["updated_at"],
            )
            for d in docs
        ]
    return RoleDocumentsBySection(sections=sections)


@router.get("/role-documents/{doc_id}", response_model=RoleDocumentOut)
async def get_document(
    doc_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> RoleDocumentOut:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    return RoleDocumentOut(**doc)


@router.get(
    "/role-documents/{doc_id}/versions",
    response_model=list[RoleDocumentOut],
)
async def list_versions_endpoint(
    doc_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> list[RoleDocumentOut]:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    versions = await role_documents.list_versions(
        doc["role_project_id"],
        str(doc["section"]),
        str(doc["name"]),
        pool=db_pool.pool,
    )
    return [RoleDocumentOut(**v) for v in versions]


@router.patch("/role-documents/{doc_id}", response_model=RoleDocumentOut)
async def update_document(
    doc_id: UUID,
    body: UpdateRoleDocumentRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> RoleDocumentOut:
    try:
        await role_documents.update_content(doc_id, body.content, pool=db_pool.pool)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    log.info("api.role_documents.updated", doc_id=str(doc_id))
    return RoleDocumentOut(**doc)


@router.post("/role-documents/{doc_id}/lock", response_model=LockResponse)
async def lock_document_endpoint(
    doc_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> LockResponse:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    await role_documents.lock_document(doc_id, pool=db_pool.pool)
    log.info("api.role_documents.locked", doc_id=str(doc_id))
    return LockResponse(status="locked")


@router.post("/role-documents/{doc_id}/unlock", response_model=LockResponse)
async def unlock_document_endpoint(
    doc_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],  # noqa: ARG001
) -> LockResponse:
    doc = await role_documents.get_by_id(doc_id, pool=db_pool.pool)
    if doc is None:
        raise HTTPException(status_code=404, detail="role document not found")
    await role_documents.unlock_document(doc_id, pool=db_pool.pool)
    log.info("api.role_documents.unlocked", doc_id=str(doc_id))
    return LockResponse(status="unlocked")
