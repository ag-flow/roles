"""DTOs Pydantic pour les source_items."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class SourceItemResponse(BaseModel):
    """Sortie API pour un source_item."""

    id: UUID
    platform_item_id: str
    title: str | None = None
    duration_s: int | None = None
    published_at: datetime | None = None
    thumbnail_url: str | None = None
    status: str
    selected: bool = False
    audio_s3_key: str | None = None
    error: str | None = None


class SelectItemsRequest(BaseModel):
    """Body POST /api/sources/{source_id}/items/select."""

    item_ids: list[UUID]
    deselect_others: bool = False
