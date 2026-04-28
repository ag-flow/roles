"""Endpoint /api/me — retourne le user courant authentifié."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from role_builder.auth.dependencies import CurrentUser, get_current_user

router = APIRouter()


@router.get("/me")
async def get_me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> dict[str, str | None]:
    """Retourne l'utilisateur courant tel qu'extrait du token (ou stub si bypass)."""
    return {
        "user_id": str(user.user_id),
        "username": user.username,
        "email": user.email,
        "tenant_id": str(user.tenant_id),
    }
