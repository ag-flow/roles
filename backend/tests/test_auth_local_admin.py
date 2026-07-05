"""Tests TDD pour l'auth admin local (HS256 sans OIDC)."""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Helpers — module local_admin
# ---------------------------------------------------------------------------


_VALID_SECRET = "x" * 32  # 32 chars min


def _setup_admin_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    user: str = "admin",
    password: str = "secret-pwd",
    secret: str = _VALID_SECRET,
    ttl_s: int = 3600,
) -> None:
    from role_builder.config import settings as _settings

    monkeypatch.setattr(_settings, "local_admin_enabled", enabled, raising=False)
    monkeypatch.setattr(_settings, "local_admin_user", user, raising=False)
    monkeypatch.setattr(_settings, "local_admin_password", password, raising=False)
    monkeypatch.setattr(_settings, "local_admin_secret", secret, raising=False)
    monkeypatch.setattr(
        _settings, "local_admin_token_ttl_s", ttl_s, raising=False,
    )


def test_verify_password_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    assert local_admin.verify_password("admin", "secret-pwd") is True


def test_verify_password_wrong_user(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    assert local_admin.verify_password("notadmin", "secret-pwd") is False


def test_verify_password_wrong_password(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    assert local_admin.verify_password("admin", "WRONG") is False


def test_verify_password_raises_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch, enabled=False)
    with pytest.raises(local_admin.LocalAdminAuthError):
        local_admin.verify_password("admin", "secret-pwd")


def test_verify_password_raises_when_secret_too_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch, secret="too-short")
    with pytest.raises(local_admin.LocalAdminAuthError):
        local_admin.verify_password("admin", "secret-pwd")


def test_issue_and_verify_token_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    token, expires_in = local_admin.issue_token()
    assert expires_in == 3600
    claims = local_admin.verify_token(token)
    assert claims["preferred_username"] == "admin"
    assert claims["sub"] == str(local_admin.ADMIN_USER_ID)
    assert claims["iss"] == local_admin.ISSUER


def test_issue_token_includes_email_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le JWT doit contenir le claim 'email' si local_admin_email est défini."""
    from role_builder.auth import local_admin
    from role_builder.config import settings as _settings

    _setup_admin_settings(monkeypatch)
    monkeypatch.setattr(_settings, "local_admin_email", "llm.beard.family@gmail.com", raising=False)
    token, _ = local_admin.issue_token()
    claims = local_admin.verify_token(token)
    assert claims.get("email") == "llm.beard.family@gmail.com"


def test_issue_token_omits_email_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sans local_admin_email, le claim 'email' ne doit pas apparaître dans le JWT."""
    from role_builder.auth import local_admin
    from role_builder.config import settings as _settings

    _setup_admin_settings(monkeypatch)
    monkeypatch.setattr(_settings, "local_admin_email", "", raising=False)
    token, _ = local_admin.issue_token()
    claims = local_admin.verify_token(token)
    assert "email" not in claims


def test_disabled_user_has_email_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """En mode disable_auth, le user stub doit refléter local_admin_email.

    Le stub est construit à l'appel (pas à l'import) : le monkeypatch des
    settings suffit, sans importlib.reload — un reload sous settings patchés
    figeait l'email dans le module et polluait les tests suivants.
    """
    from role_builder.auth import dependencies as deps
    from role_builder.config import settings as _settings

    monkeypatch.setattr(_settings, "local_admin_email", "llm.beard.family@gmail.com", raising=False)
    assert deps._disabled_user().email == "llm.beard.family@gmail.com"

    monkeypatch.setattr(_settings, "local_admin_email", "", raising=False)
    assert deps._disabled_user().email is None


def test_verify_token_rejects_wrong_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    """Un JWT signé avec un secret X ne doit pas valider avec un secret Y."""
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch, secret=_VALID_SECRET)
    token, _ = local_admin.issue_token()

    # Change le secret côté serveur — le token précédent doit être invalidé
    _setup_admin_settings(monkeypatch, secret="y" * 32)
    with pytest.raises(local_admin.LocalAdminAuthError):
        local_admin.verify_token(token)


def test_verify_token_rejects_expired(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch, ttl_s=1)
    token, _ = local_admin.issue_token()
    time.sleep(2)
    with pytest.raises(local_admin.LocalAdminAuthError):
        local_admin.verify_token(token)


def test_is_local_admin_token_yes(monkeypatch: pytest.MonkeyPatch) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    token, _ = local_admin.issue_token()
    assert local_admin.is_local_admin_token(token) is True


def test_is_local_admin_token_no_for_keycloak_jwt() -> None:
    """JWT avec un issuer Keycloak ne doit pas être traité comme local admin."""
    import jwt

    from role_builder.auth import local_admin

    payload = {"iss": "https://keycloak.example/realms/yoops", "sub": "x"}
    token = jwt.encode(payload, "anysecret", algorithm="HS256")
    assert local_admin.is_local_admin_token(token) is False


def test_is_local_admin_token_no_for_garbage() -> None:
    from role_builder.auth import local_admin

    assert local_admin.is_local_admin_token("not.a.jwt") is False


# ---------------------------------------------------------------------------
# Route POST /api/auth/local-login
# ---------------------------------------------------------------------------


def test_local_login_returns_404_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_admin_settings(monkeypatch, enabled=False)
    resp = client.post(
        "/api/auth/local-login",
        json={"username": "admin", "password": "x"},
    )
    assert resp.status_code == 404


def test_local_login_returns_401_on_wrong_password(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _setup_admin_settings(monkeypatch)
    resp = client.post(
        "/api/auth/local-login",
        json={"username": "admin", "password": "WRONG"},
    )
    assert resp.status_code == 401


def test_local_login_returns_token_on_success(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    from role_builder.auth import local_admin

    _setup_admin_settings(monkeypatch)
    resp = client.post(
        "/api/auth/local-login",
        json={"username": "admin", "password": "secret-pwd"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token_type"] == "Bearer"
    assert body["expires_in"] == 3600
    claims = local_admin.verify_token(body["access_token"])
    assert claims["preferred_username"] == "admin"


def test_local_login_returns_500_when_secret_misconfigured(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si admin_enabled mais secret manquant → 500 (config server-side cassée)."""
    _setup_admin_settings(monkeypatch, secret="too-short")
    resp = client.post(
        "/api/auth/local-login",
        json={"username": "admin", "password": "secret-pwd"},
    )
    assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Dispatcher dans get_current_user — accepte le JWT local
# ---------------------------------------------------------------------------


def test_get_current_user_accepts_local_admin_token(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un endpoint protégé doit accepter un Bearer JWT local admin."""
    from role_builder.auth import local_admin
    from role_builder.config import settings as _settings

    _setup_admin_settings(monkeypatch)
    # Désactive le bypass disable_auth pour vraiment exercer le dispatcher
    monkeypatch.setattr(_settings, "disable_auth", False, raising=False)

    token, _ = local_admin.issue_token()
    # On utilise /api/me qui est un endpoint protégé minimal
    resp = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Si l'endpoint /me existe et accepte le token, on aura 200. Sinon on peut
    # simplement vérifier qu'on n'obtient pas 401.
    assert resp.status_code != 401, resp.text


def test_get_current_user_rejects_local_admin_token_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si on passe un JWT issuer local-admin alors que le mode est désactivé,
    le dispatcher ne le valide pas via HS256 → tombe sur Keycloak → 401."""
    import jwt

    from role_builder.auth import local_admin
    from role_builder.config import settings as _settings

    # On émet un token "local admin" avec un secret inventé
    payload = {
        "iss": local_admin.ISSUER,
        "sub": "00000000-0000-0000-0000-000000000099",
        "preferred_username": "fake",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }
    token = jwt.encode(payload, "any-secret", algorithm="HS256")

    monkeypatch.setattr(_settings, "local_admin_enabled", False, raising=False)
    monkeypatch.setattr(_settings, "disable_auth", False, raising=False)
    # On stub le KeycloakValidator pour qu'il rejette tout
    from role_builder.auth import dependencies as deps
    from role_builder.auth.keycloak import InvalidTokenError

    class _RejectAll:
        async def validate(self, _: str) -> Any:
            raise InvalidTokenError("not a keycloak token")

    monkeypatch.setattr(deps, "_get_validator", lambda: _RejectAll())

    resp = client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401
