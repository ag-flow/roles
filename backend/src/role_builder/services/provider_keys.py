"""Résolution de la clé API provider injectée dans un worker de transcription.

Priorité : le secret de l'utilisateur (via SecretStore), sinon la clé machine
partagée du .env (fallback opérateur, décision de cadrage 2026-07-05).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog

from role_builder.config import settings
from role_builder.services.secret_store import (
    get_secret_store as _get_secret_store,
)

log = structlog.get_logger(__name__)

# Mapping provider name (kebab-case côté DB) -> attribut Settings (snake_case).
# Fallback machine (.env) quand la clé user n'a pas de secret résolvable.
# Doit couvrir TRANSCRIPTION_PROVIDER_TYPES (test anti-drift dédié).
PROVIDER_TO_SETTINGS_ATTR: dict[str, str] = {
    "openai-whisper": "openai_api_key",
    "deepgram": "deepgram_api_key",
    "assemblyai": "assemblyai_api_key",
    "speechmatics": "speechmatics_api_key",
    # faster-whisper local : pas d'API key requise (modèle embarqué).
    "faster-whisper": "",
}


def provider_env_key(provider: str) -> str:
    """Env var attendue par le worker côté container pour un provider donné."""
    # `openai-whisper` → `OPENAI_API_KEY`
    base = provider.split("-", 1)[0].upper()
    return f"{base}_API_KEY"


async def resolve_provider_api_key(
    *,
    user_id: UUID,
    key: dict[str, Any],
    provider: str,
    pool: asyncpg.Pool,
) -> str:
    """Clé provider du user (via son secret), sinon fallback machine (.env)."""
    if key.get("secret_id") is not None:
        value = await _get_secret_store().read_secret_by_id(
            secret_id=key["secret_id"], user_id=user_id, pool=pool
        )
        if value:
            return value
        log.warning(
            "provider_keys.secret_unresolvable",
            user_id=str(user_id),
            provider=provider,
        )
    api_attr = PROVIDER_TO_SETTINGS_ATTR.get(provider, "")
    if api_attr:
        return getattr(settings, api_attr, "") or ""
    return ""
