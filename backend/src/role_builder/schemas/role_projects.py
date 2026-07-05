"""Schémas Pydantic pour les role_projects."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class RoleProjectOut(BaseModel):
    """DTO de sortie pour un role_project (liste page d'accueil)."""

    model_config = ConfigDict(extra="allow")

    id: UUID
    tenant_id: UUID
    user_id: UUID
    display_name: str
    description: str | None = None
    created_at: datetime
    updated_at: datetime
