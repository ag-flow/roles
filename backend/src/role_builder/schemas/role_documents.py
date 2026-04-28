"""DTOs Pydantic pour les role_documents (Sprint 7 Phase D)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class RoleDocumentOut(BaseModel):
    """Document complet (avec contenu) — pour detail + versions endpoints."""

    id: UUID
    role_project_id: UUID
    section: str
    name: str
    content: str
    version: int
    is_current: bool
    locked: bool
    source_run_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class RoleDocumentSummary(BaseModel):
    """Variante allégée (sans ``content``) pour les listings groupés."""

    id: UUID
    section: str
    name: str
    version: int
    is_current: bool
    locked: bool
    updated_at: datetime


class RoleDocumentsBySection(BaseModel):
    """Réponse de GET /role-projects/{id}/role-documents — groupé par section."""

    sections: dict[str, list[RoleDocumentSummary]]


class UpdateRoleDocumentRequest(BaseModel):
    """Body de PATCH /role-documents/{id}."""

    content: str = Field(min_length=1)


class LockResponse(BaseModel):
    status: str
