"""FastAPI dependencies pour l'auth Keycloak.

Expose `get_current_user`, qui valide l'access token Bearer et renvoie un
`CurrentUser`. Mode bypass via `settings.disable_auth=True` pour les tests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from fastapi import Header, HTTPException, status

from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator
from role_builder.config import TENANT_ID_DEFAULT, settings


@dataclass
class CurrentUser:
    """Représente l'utilisateur authentifié pour la requête courante."""

    user_id: UUID
    username: str
    email: str | None
    tenant_id: UUID
    raw_token: dict[str, Any] = field(default_factory=dict)


_validator: KeycloakValidator | None = None


def _get_validator() -> KeycloakValidator:
    """Singleton validator construit à la première utilisation."""
    global _validator
    if _validator is None:
        _validator = KeycloakValidator(
            issuer_url=settings.keycloak_issuer_url,
            audience=settings.keycloak_audience or settings.keycloak_client_id,
        )
    return _validator


_DISABLED_USER = CurrentUser(
    user_id=UUID("00000000-0000-0000-0000-000000000001"),
    username="dev-disabled-auth",
    email=None,
    tenant_id=TENANT_ID_DEFAULT,
    raw_token={},
)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """FastAPI dep : valide le Bearer token et retourne le `CurrentUser`.

    - Si `settings.disable_auth=True` → renvoie `_DISABLED_USER` (tests/dev).
    - Header absent ou non-Bearer → 401.
    - Token invalide (signature, exp, claims) → 401.
    """
    if settings.disable_auth:
        return _DISABLED_USER

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = authorization[len("Bearer ") :]
    try:
        claims = await _get_validator().validate(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        user_id=UUID(claims["sub"]),
        username=claims.get("preferred_username", ""),
        email=claims.get("email"),
        tenant_id=TENANT_ID_DEFAULT,
        raw_token=claims,
    )


async def authenticate_websocket(token: str | None) -> CurrentUser:
    """Valide un access token passé en query param ``?token=`` au handshake WS.

    Les WebSockets ne supportent pas les headers custom au handshake côté
    navigateur — on passe donc le bearer dans l'URL (chiffré en TLS prod).

    - Si ``settings.disable_auth=True`` → renvoie ``_DISABLED_USER``.
    - Token absent ou invalide → lève ``InvalidTokenError``.

    L'appelant (``routes.websocket``) doit appeler cette fonction AVANT
    ``ws.accept()`` et fermer la WS avec close code 1008 (Policy Violation)
    en cas d'échec.
    """
    if settings.disable_auth:
        return _DISABLED_USER

    if not token:
        raise InvalidTokenError("missing token")

    claims = await _get_validator().validate(token)
    return CurrentUser(
        user_id=UUID(claims["sub"]),
        username=claims.get("preferred_username", ""),
        email=claims.get("email"),
        tenant_id=TENANT_ID_DEFAULT,
        raw_token=claims,
    )
