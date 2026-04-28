"""Schémas Pydantic pour les endpoints credentials (comptes réseaux sociaux)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class UserCredentialOut(BaseModel):
    id: UUID
    platform: str
    label: str | None
    status: str
    last_validated_at: datetime | None
    expires_at: datetime | None
    created_at: datetime


class CreateCredentialRequest(BaseModel):
    platform: Literal["youtube", "instagram", "tiktok"]
    label: str | None = None
    cookies_b64: str


class TestCredentialResponse(BaseModel):
    status: str
    last_validated_at: datetime | None
    error: str | None = None
