"""Auth local admin — JWT HS256 émis et validé localement (sans OIDC).

Activé via ``settings.local_admin_enabled=True`` et ``settings.local_admin_password``
non vide. Permet à un admin de se connecter avec un user/pwd stockés en .env
sans dépendre de Keycloak. Les JWT émis ici cohabitent avec les JWT Keycloak :
le dispatcher dans ``auth.dependencies.get_current_user`` choisit la bonne
méthode de validation selon le claim ``iss``.

Sécurité :
- ``local_admin_password`` est comparé en constant-time pour éviter le timing.
- Le secret HS256 (``local_admin_secret``) doit faire au moins 32 caractères.
- Le user_id est dérivé de manière déterministe via ``uuid5(NAMESPACE_DNS, ...)``
  pour que les données soient toujours rattachées au même owner DB.
"""

from __future__ import annotations

import hmac
import time
from uuid import NAMESPACE_DNS, UUID, uuid5

import jwt

from role_builder.config import settings

# ID stable de l'admin local (déterministe à partir du nom). Permet aux données
# créées par l'admin local de toujours pointer sur la même row si on coexiste
# avec des users Keycloak.
ADMIN_USER_ID: UUID = uuid5(NAMESPACE_DNS, "agflow.roles.local-admin")

ISSUER = "agflow-roles-local-admin"


class LocalAdminAuthError(Exception):
    """Levée quand les creds sont mauvais ou la config absente."""


def _ensure_configured() -> None:
    if not settings.local_admin_enabled:
        raise LocalAdminAuthError("local admin auth disabled")
    if not settings.local_admin_password:
        raise LocalAdminAuthError("local_admin_password not set")
    if not settings.local_admin_secret or len(settings.local_admin_secret) < 32:
        raise LocalAdminAuthError(
            "local_admin_secret must be at least 32 characters",
        )


def verify_password(username: str, password: str) -> bool:
    """Vérifie que (username, password) correspondent au compte admin local."""
    _ensure_configured()
    if username != settings.local_admin_user:
        # Compare quand même un dummy pour timing constant
        hmac.compare_digest("x", "y")
        return False
    return hmac.compare_digest(password, settings.local_admin_password)


def issue_token() -> tuple[str, int]:
    """Émet un JWT HS256 pour l'admin local. Retourne (token, expires_in_seconds)."""
    _ensure_configured()
    now = int(time.time())
    exp = now + settings.local_admin_token_ttl_s
    payload = {
        "iss": ISSUER,
        "sub": str(ADMIN_USER_ID),
        "preferred_username": settings.local_admin_user,
        "iat": now,
        "exp": exp,
    }
    token = jwt.encode(payload, settings.local_admin_secret, algorithm="HS256")
    return token, settings.local_admin_token_ttl_s


def is_local_admin_token(token: str) -> bool:
    """Inspecte le claim ``iss`` SANS valider la signature.

    Permet au dispatcher de choisir la méthode de validation (HS256 local ou
    RS256 Keycloak) avant de tomber sur une erreur de signature.
    """
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
    except jwt.InvalidTokenError:
        return False
    return unverified.get("iss") == ISSUER


def verify_token(token: str) -> dict:
    """Valide signature + exp + issuer. Retourne les claims.

    Lève ``LocalAdminAuthError`` si invalide.
    """
    _ensure_configured()
    try:
        claims = jwt.decode(
            token,
            settings.local_admin_secret,
            algorithms=["HS256"],
            issuer=ISSUER,
            options={"require": ["exp", "iat", "iss", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        raise LocalAdminAuthError(f"invalid local admin token: {exc}") from exc
    return claims
