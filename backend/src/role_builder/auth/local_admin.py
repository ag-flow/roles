"""Auth local admin — JWT HS256 émis et validé localement (sans OIDC).

Activé via ``settings.local_admin_enabled=True`` et ``settings.local_admin_password``
non vide. Permet à un admin de se connecter avec un user/pwd stockés en .env
sans dépendre de Keycloak. Les JWT émis ici cohabitent avec les JWT Keycloak :
le dispatcher dans ``auth.dependencies.get_current_user`` choisit la bonne
méthode de validation selon le claim ``iss``.

Sécurité :
- ``local_admin_password`` est comparé en constant-time pour éviter le timing.
- Le secret HS256 (``local_admin_secret``) doit faire au moins 32 caractères.
"""

from __future__ import annotations

import hmac
import time
from uuid import UUID

import jwt

from role_builder.config import settings

# ID stable de l'admin local. Identique au user stub ``_disabled_user()`` de
# ``auth.dependencies`` pour garantir la continuité avec les données créées
# pendant la phase ``DISABLE_AUTH=true`` du MVP : les projets stockés sous
# cet UUID restent visibles à l'admin local après le passage en vrai
# mode auth.
ADMIN_USER_ID: UUID = UUID("00000000-0000-0000-0000-000000000001")

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
    payload: dict = {
        "iss": ISSUER,
        "sub": str(ADMIN_USER_ID),
        "preferred_username": settings.local_admin_user,
        "iat": now,
        "exp": exp,
    }
    if settings.local_admin_email:
        payload["email"] = settings.local_admin_email
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
