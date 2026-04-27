"""DTOs Pydantic pour les prompts et leurs versions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class PromptOut(BaseModel):
    id: UUID
    name: str
    type: str
    target_section: str | None = None
    description: str | None = None


class PromptVersionOut(BaseModel):
    id: UUID
    prompt_id: UUID
    version_number: int
    template: str
    is_system_default: bool
    created_at: datetime


class CreateVersionRequest(BaseModel):
    template: str
