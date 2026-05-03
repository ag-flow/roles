"""DTOs Pydantic pour les routes transcription_keys."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class TranscriptionKeyOut(BaseModel):
    id: UUID
    provider: str
    label: str | None
    status: str
    is_primary: bool
    is_fallback: bool
    workers_count: int
    monthly_cap_usd: float | None
    current_month_spend_usd: float
    current_balance_usd: float | None
    last_balance_check_at: datetime | None
    last_validated_at: datetime | None
    created_at: datetime


class CreateTranscriptionKeyRequest(BaseModel):
    provider: Literal["openai-whisper", "deepgram", "assemblyai", "speechmatics"]
    label: str | None = None
    api_key: str
    harpocrate_key: str = Field(min_length=1)
    workers_count: int = Field(default=1, ge=1, le=5)
    is_primary: bool = False
    is_fallback: bool = False


class UpdateTranscriptionKeyRequest(BaseModel):
    workers_count: int | None = Field(default=None, ge=1, le=5)
    is_primary: bool | None = None
    is_fallback: bool | None = None


class UpdateQuotaRequest(BaseModel):
    monthly_cap_usd: float | None = Field(default=None, ge=0)


class TestKeyResponse(BaseModel):
    status: str
    last_validated_at: datetime | None
    balance_usd: float | None
    error: str | None = None


class UsageResponse(BaseModel):
    current_month_spend_usd: float
    monthly_cap_usd: float | None
    pct_used: float | None
    last_balance_check_at: datetime | None
    current_balance_usd: float | None
