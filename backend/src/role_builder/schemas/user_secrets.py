"""Schémas Pydantic pour les endpoints secrets utilisateur."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

# Enum fixe des types de secrets (décision de cadrage 2026-07-05) — aligné
# sur le CHECK de la migration 0009.
SecretType = Literal[
    "openai-whisper",
    "deepgram",
    "assemblyai",
    "speechmatics",
    "youtube-cookies",
    "instagram-cookies",
    "tiktok-cookies",
]

# Types utilisables comme clé de transcription (le type EST le provider).
TRANSCRIPTION_PROVIDER_TYPES = frozenset(
    {"openai-whisper", "deepgram", "assemblyai", "speechmatics"}
)

_COOKIES_SUFFIX = "-cookies"


def cookies_platform(secret_type: str) -> str | None:
    """Plateforme d'un type cookies ('youtube-cookies' → 'youtube'), sinon None."""
    if secret_type.endswith(_COOKIES_SUFFIX):
        return secret_type.removesuffix(_COOKIES_SUFFIX)
    return None


class SecretOut(BaseModel):
    """Ni valeur ni chemin wallet : seules les métadonnées sortent de l'API."""

    id: UUID
    secret_type: str
    label: str
    storage: str
    wallet_id: UUID | None
    status: str
    created_at: datetime


class CreateSecretRequest(BaseModel):
    secret_type: SecretType
    label: str = Field(min_length=1)
    value: str = Field(min_length=1)
    # None = stockage local (champ chiffré en base)
    wallet_id: UUID | None = None
