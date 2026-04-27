"""Tests for auth.keycloak — JWKS cache + RS256 JWT validation via PyJWT."""
from __future__ import annotations

import time
from typing import Any
from unittest.mock import MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@pytest.fixture()
def rsa_keypair() -> tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey]:
    """Generate an in-memory RSA keypair for signing test tokens."""
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return priv, priv.public_key()


def _priv_pem(priv: rsa.RSAPrivateKey) -> bytes:
    return priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def _pub_pem(pub: rsa.RSAPublicKey) -> bytes:
    return pub.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _make_token(
    priv: rsa.RSAPrivateKey, claims: dict[str, Any], kid: str = "testkid"
) -> str:
    return jwt.encode(claims, _priv_pem(priv), algorithm="RS256", headers={"kid": kid})


def _patch_signing_key(
    monkeypatch: pytest.MonkeyPatch, public_key: rsa.RSAPublicKey
) -> None:
    """Patch PyJWKClient.get_signing_key_from_jwt to return our test public key."""
    from jwt import PyJWKClient

    pem = _pub_pem(public_key)

    def fake_get_signing_key(self: PyJWKClient, token: str) -> Any:  # noqa: ARG001
        return MagicMock(key=pem)

    monkeypatch.setattr(PyJWKClient, "get_signing_key_from_jwt", fake_get_signing_key)


async def test_validate_returns_claims_for_valid_token(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A correctly signed, fresh token returns the decoded claims."""
    from role_builder.auth.keycloak import KeycloakValidator

    priv, pub = rsa_keypair
    _patch_signing_key(monkeypatch, pub)

    issuer = "https://security.yoops.org/realms/yoops"
    audience = "agflow-roles"
    now = int(time.time())
    token = _make_token(
        priv,
        {
            "iss": issuer,
            "aud": audience,
            "sub": "00000000-0000-0000-0000-0000000000aa",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "iat": now,
            "exp": now + 60,
        },
    )

    validator = KeycloakValidator(issuer_url=issuer, audience=audience)
    payload = await validator.validate(token)
    assert payload["sub"] == "00000000-0000-0000-0000-0000000000aa"
    assert payload["preferred_username"] == "alice"
    assert payload["email"] == "alice@example.com"


async def test_validate_rejects_expired_token(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token whose exp is in the past raises InvalidTokenError."""
    from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator

    priv, pub = rsa_keypair
    _patch_signing_key(monkeypatch, pub)

    issuer = "https://security.yoops.org/realms/yoops"
    audience = "agflow-roles"
    now = int(time.time())
    token = _make_token(
        priv,
        {
            "iss": issuer,
            "aud": audience,
            "sub": "00000000-0000-0000-0000-0000000000aa",
            "iat": now - 600,
            "exp": now - 60,
        },
    )

    validator = KeycloakValidator(issuer_url=issuer, audience=audience)
    with pytest.raises(InvalidTokenError):
        await validator.validate(token)


async def test_validate_rejects_wrong_issuer(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Issuer claim mismatch raises InvalidTokenError."""
    from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator

    priv, pub = rsa_keypair
    _patch_signing_key(monkeypatch, pub)

    issuer = "https://security.yoops.org/realms/yoops"
    audience = "agflow-roles"
    now = int(time.time())
    token = _make_token(
        priv,
        {
            "iss": "https://evil.example.com/realms/yoops",
            "aud": audience,
            "sub": "00000000-0000-0000-0000-0000000000aa",
            "iat": now,
            "exp": now + 60,
        },
    )

    validator = KeycloakValidator(issuer_url=issuer, audience=audience)
    with pytest.raises(InvalidTokenError):
        await validator.validate(token)


async def test_validate_rejects_wrong_audience(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Audience claim mismatch raises InvalidTokenError."""
    from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator

    priv, pub = rsa_keypair
    _patch_signing_key(monkeypatch, pub)

    issuer = "https://security.yoops.org/realms/yoops"
    audience = "agflow-roles"
    now = int(time.time())
    token = _make_token(
        priv,
        {
            "iss": issuer,
            "aud": "some-other-client",
            "sub": "00000000-0000-0000-0000-0000000000aa",
            "iat": now,
            "exp": now + 60,
        },
    )

    validator = KeycloakValidator(issuer_url=issuer, audience=audience)
    with pytest.raises(InvalidTokenError):
        await validator.validate(token)


async def test_validate_rejects_token_signed_with_wrong_key(
    rsa_keypair: tuple[rsa.RSAPrivateKey, rsa.RSAPublicKey],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token signed by a key that doesn't match the JWKS public key fails."""
    from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator

    _, pub = rsa_keypair
    # Use a different private key to sign the token
    other_priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _patch_signing_key(monkeypatch, pub)  # JWKS still serves `pub`

    issuer = "https://security.yoops.org/realms/yoops"
    audience = "agflow-roles"
    now = int(time.time())
    token = _make_token(
        other_priv,
        {
            "iss": issuer,
            "aud": audience,
            "sub": "00000000-0000-0000-0000-0000000000aa",
            "iat": now,
            "exp": now + 60,
        },
    )

    validator = KeycloakValidator(issuer_url=issuer, audience=audience)
    with pytest.raises(InvalidTokenError):
        await validator.validate(token)


async def test_validate_rejects_malformed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-JWT string raises InvalidTokenError."""
    from role_builder.auth.keycloak import InvalidTokenError, KeycloakValidator

    # Patch to a dummy key so the failure path is parse / signature, not JWKS fetch
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _patch_signing_key(monkeypatch, priv.public_key())

    validator = KeycloakValidator(
        issuer_url="https://security.yoops.org/realms/yoops",
        audience="agflow-roles",
    )
    with pytest.raises(InvalidTokenError):
        await validator.validate("not-a-jwt-at-all")
