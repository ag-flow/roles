"""Schémas Pydantic pour les endpoints wallets (coffres Harpocrate personnels)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class WalletOut(BaseModel):
    """Le token n'est jamais exposé, même chiffré."""

    id: UUID
    label: str
    api_url: str
    status: str
    created_at: datetime


class CreateWalletRequest(BaseModel):
    label: str = Field(min_length=1)
    api_token: str = Field(min_length=1)
    api_url: str = "https://vault.yoops.org"
