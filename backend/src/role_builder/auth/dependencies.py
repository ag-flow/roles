"""FastAPI dependencies pour l'auth (Keycloak OIDC + admin local optionnel).

Expose ``get_current_user``, qui valide l'access token Bearer et renvoie un
``CurrentUser``. Trois modes :

1. ``settings.disable_auth=True`` → bypass total (tests/dev), retourne un user fixe.
2. JWT issuer ``"agflow-roles-local-admin"`` → validation HS256 locale
   (cf. ``role_builder.auth.local_admin``). Activé via ``settings.local_admin_enabled``.
3. JWT Keycloak (RS256, JWKS) → validation OIDC standard.

Le dispatcher inspecte le claim ``iss`` SANS valider la signature pour choisir
la bonne méthode, puis valide proprement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any
from uuid import UUID

from fastapi import Header, HTTPException, status

from role_builder.auth import local_admin
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


def _claims_to_user(claims: dict[str, Any]) -> CurrentUser:
    return CurrentUser(
        user_id=UUID(claims["sub"]),
        username=claims.get("preferred_username", ""),
        email=claims.get("email"),
        tenant_id=TENANT_ID_DEFAULT,
        raw_token=claims,
    )


async def _validate_token(token: str) -> dict[str, Any]:
    """Dispatch local admin (HS256) vs Keycloak (RS256) selon le claim ``iss``."""
    if settings.local_admin_enabled and local_admin.is_local_admin_token(token):
        try:
            return local_admin.verify_token(token)
        except local_admin.LocalAdminAuthError as exc:
            raise InvalidTokenError(str(exc)) from exc
    return await _get_validator().validate(token)


async def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
) -> CurrentUser:
    """FastAPI dep : valide le Bearer token et retourne le `CurrentUser`."""
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
        claims = await _validate_token(token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return _claims_to_user(claims)


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

    claims = await _validate_token(token)
    return _claims_to_user(claims)
