"""Schémas Pydantic pour les endpoints credentials (comptes réseaux sociaux)."""

from __future__ import annotations

from datetime import datetime
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
    """Le credential référence un secret cookies déjà saisi (/api/secrets).

    La plateforme est dérivée du secret_type ('youtube-cookies' → 'youtube').
    """

    secret_id: UUID
    label: str | None = None


class TestCredentialResponse(BaseModel):
    status: str
    last_validated_at: datetime | None
    error: str | None = None
