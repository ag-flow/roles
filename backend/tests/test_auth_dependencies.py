"""Tests for auth.dependencies — FastAPI get_current_user dep + bypass."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException


async def test_disable_auth_returns_default_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When settings.disable_auth is True, returns the static stub user."""
    from role_builder.auth import dependencies as deps
    from role_builder.config import TENANT_ID_DEFAULT, settings

    monkeypatch.setattr(settings, "disable_auth", True, raising=False)
    user = await deps.get_current_user(authorization=None)
    assert user.username == "dev-disabled-auth"
    assert user.tenant_id == TENANT_ID_DEFAULT
    assert user.email is None


async def test_missing_authorization_header_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No Authorization header → HTTPException 401."""
    from role_builder.auth import dependencies as deps
    from role_builder.config import settings

    monkeypatch.setattr(settings, "disable_auth", False, raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(authorization=None)
    assert exc_info.value.status_code == 401


async def test_non_bearer_authorization_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Authorization header without 'Bearer ' prefix → 401."""
    from role_builder.auth import dependencies as deps
    from role_builder.config import settings

    monkeypatch.setattr(settings, "disable_auth", False, raising=False)
    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(authorization="Basic abc123")
    assert exc_info.value.status_code == 401


async def test_invalid_token_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator that raises InvalidTokenError → HTTPException 401."""
    from role_builder.auth import dependencies as deps
    from role_builder.auth.keycloak import InvalidTokenError
    from role_builder.config import settings

    monkeypatch.setattr(settings, "disable_auth", False, raising=False)

    class _StubValidator:
        async def validate(self, token: str) -> dict[str, Any]:  # noqa: ARG002
            raise InvalidTokenError("bad signature")

    monkeypatch.setattr(deps, "_validator", _StubValidator())

    with pytest.raises(HTTPException) as exc_info:
        await deps.get_current_user(authorization="Bearer junk")
    assert exc_info.value.status_code == 401


async def test_valid_token_returns_current_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Validator that returns claims → CurrentUser populated from sub/preferred_username/email."""
    from role_builder.auth import dependencies as deps
    from role_builder.config import TENANT_ID_DEFAULT, settings

    monkeypatch.setattr(settings, "disable_auth", False, raising=False)

    expected_claims = {
        "sub": "11111111-2222-3333-4444-555555555555",
        "preferred_username": "alice",
        "email": "alice@example.com",
        "iat": 1700000000,
        "exp": 1700001000,
    }

    class _StubValidator:
        async def validate(self, token: str) -> dict[str, Any]:  # noqa: ARG002
            return expected_claims

    monkeypatch.setattr(deps, "_validator", _StubValidator())

    user = await deps.get_current_user(authorization="Bearer good-token")
    assert str(user.user_id) == "11111111-2222-3333-4444-555555555555"
    assert user.username == "alice"
    assert user.email == "alice@example.com"
    assert user.tenant_id == TENANT_ID_DEFAULT
    assert user.raw_token == expected_claims
