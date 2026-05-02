"""Endpoint d'authentification locale (admin sans OIDC).

POST /api/auth/local-login — body: {username, password} → 200 {access_token, token_type, expires_in}.
Désactivé (404 sur tout) si ``settings.local_admin_enabled`` est false.
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from role_builder.auth import local_admin
from role_builder.config import settings

router = APIRouter()
log = structlog.get_logger(__name__)


class LocalLoginRequest(BaseModel):
    username: str
    password: str


class LocalLoginResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int


@router.post(
    "/auth/local-login",
    response_model=LocalLoginResponse,
)
async def local_login(body: LocalLoginRequest) -> LocalLoginResponse:
    """Valide username/password contre les creds .env et retourne un JWT local."""
    if not settings.local_admin_enabled:
        # On répond 404 plutôt que 401 quand le mode est désactivé : c'est plus
        # discret et évite de signaler l'existence du endpoint en prod.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    try:
        ok = local_admin.verify_password(body.username, body.password)
    except local_admin.LocalAdminAuthError as exc:
        # Mauvaise config côté serveur → 500, pas 401.
        log.error("local_admin.misconfigured", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="local admin not configured properly",
        ) from exc

    if not ok:
        log.warning("local_admin.login_failed", username=body.username)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )

    token, expires_in = local_admin.issue_token()
    log.info("local_admin.login_succeeded", username=body.username)
    return LocalLoginResponse(access_token=token, expires_in=expires_in)
