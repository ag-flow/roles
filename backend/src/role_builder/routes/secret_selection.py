"""Résolution du secret sélectionné par une définition de service.

Bloc commun aux routes transcription-keys et credentials : le POST reçoit un
secret_id, il faut vérifier l'existence (scoping user), le type attendu, puis
obtenir la valeur — avec la même sémantique d'erreurs HTTP des deux côtés.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from role_builder.db_helpers import user_secrets as secrets_helper
from role_builder.schemas.user_secrets import (
    TRANSCRIPTION_PROVIDER_TYPES,
    cookies_platform,
)
from role_builder.services.secret_store import (
    get_secret_store as _get_secret_store,
)


def _check_type(secret_type: str, expected_kind: str) -> None:
    if expected_kind == "transcription":
        if secret_type not in TRANSCRIPTION_PROVIDER_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"secret de type '{secret_type}' — attendu une clé de transcription",
            )
    elif expected_kind == "cookies":
        if cookies_platform(secret_type) is None:
            raise HTTPException(
                status_code=400,
                detail=f"secret de type '{secret_type}' — attendu des cookies",
            )
    else:  # pragma: no cover — garde de programmation
        raise ValueError(f"expected_kind inconnu : {expected_kind}")


async def resolve_selected_secret(
    *,
    secret_id: UUID,
    user_id: UUID,
    expected_kind: str,
    pool: asyncpg.Pool,
) -> tuple[dict[str, Any], str]:
    """Retourne (ligne user_secrets, valeur en clair) ou lève 404/400."""
    secret = await secrets_helper.get_secret(
        secret_id=secret_id, user_id=user_id, pool=pool
    )
    if secret is None:
        raise HTTPException(status_code=404, detail="secret not found")

    _check_type(secret["secret_type"], expected_kind)

    value = await _get_secret_store().read_value(secret, pool=pool)
    if value is None:
        raise HTTPException(
            status_code=400,
            detail="valeur du secret inaccessible (disparue du wallet ?)",
        )
    return secret, value
