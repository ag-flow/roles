"""DTO de sortie pour la table runs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RunOut(BaseModel):
    id: UUID
    role_project_id: UUID
    prompt_version_id: UUID
    status: str
    output: str | None
    llm_provider: str | None
    llm_model: str | None
    tokens_input: int | None
    tokens_output: int | None
    cost_usd: float | None
    instruction_override: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    is_obsolete: bool = False
    created_at: datetime
