"""DTOs Pydantic pour les sources."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, HttpUrl

PlatformLiteral = Literal["youtube", "instagram", "tiktok"]
SourceTypeLiteral = Literal["single", "channel", "playlist", "account"]


class CreateSourceRequest(BaseModel):
    """Body POST /api/role-projects/{role_project_id}/sources."""

    url: HttpUrl
    platform: PlatformLiteral
    source_type: SourceTypeLiteral
    credentials_id: UUID | None = None  # Sprint 2 : ignored (cookies via env vars)


class SourceResponse(BaseModel):
    """Sortie API pour une source."""

    id: UUID
    role_project_id: UUID
    platform: str
    source_type: str
    url: str
    status: str
    discovered_count: int | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime
