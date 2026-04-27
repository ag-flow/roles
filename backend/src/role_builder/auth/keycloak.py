"""Keycloak JWT validation : JWKS fetch/cache + RS256 verify + claims check."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient


class InvalidTokenError(Exception):
    """Token rejected (signature, claims, expiration, JWKS, etc.)."""


@dataclass
class KeycloakValidator:
    """Validate Keycloak access tokens (RS256) using a cached JWKS client."""

    issuer_url: str
    audience: str
    jwks_ttl_s: int = 3600
    _jwks_client: PyJWKClient | None = field(default=None, init=False, repr=False)
    _jwks_fetched_at: float = field(default=0.0, init=False, repr=False)

    @property
    def jwks_uri(self) -> str:
        return f"{self.issuer_url}/protocol/openid-connect/certs"

    def _ensure_jwks_fresh(self) -> PyJWKClient:
        """Lazily build / refresh the JWKS client every `jwks_ttl_s` seconds."""
        if (
            self._jwks_client is None
            or (time.time() - self._jwks_fetched_at) > self.jwks_ttl_s
        ):
            self._jwks_client = PyJWKClient(self.jwks_uri)
            self._jwks_fetched_at = time.time()
        return self._jwks_client

    async def validate(self, token: str) -> dict[str, Any]:
        """Validate the token and return decoded claims.

        Raises:
            InvalidTokenError: on any failure (signature, expired, claims,
                               JWKS network error, malformed token, etc.).
        """
        try:
            client = self._ensure_jwks_fresh()
            signing_key = client.get_signing_key_from_jwt(token).key
            payload: dict[str, Any] = jwt.decode(
                token,
                signing_key,
                algorithms=["RS256"],
                audience=self.audience,
                issuer=self.issuer_url,
                options={"require": ["exp", "iat", "sub"]},
            )
            return payload
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc
        except httpx.HTTPError as exc:
            raise InvalidTokenError(f"jwks fetch error: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 — defensive: any other failure → invalid
            raise InvalidTokenError(f"unexpected validation error: {exc}") from exc
