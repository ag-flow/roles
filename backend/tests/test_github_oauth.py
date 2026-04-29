"""Tests unitaires de services/github_publish/oauth.py (Sprint 8).

Le test d'intégration via les routes (test_github_auth_route.py) couvre
l'orchestration. Ici on vérifie que les requêtes HTTP vers GitHub sont bien
formées (URL, query params, body, headers).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_build_authorize_url_includes_required_params(stubbed_env: None) -> None:
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    url = client.build_authorize_url("my-state")
    assert "https://github.com/login/oauth/authorize?" in url
    assert "state=my-state" in url
    assert "scope=public_repo" in url
    assert "client_id=" in url
    assert "redirect_uri=" in url


@pytest.mark.asyncio
async def test_exchange_code_posts_form_with_secret_and_returns_token(
    stubbed_env: None,
) -> None:
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(
        200,
        json={"access_token": "ghp_xxx", "token_type": "bearer"},
        request=httpx.Request("POST", "https://github.com/login/oauth/access_token"),
    )
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake_resp)) as post_mock:  # noqa: SLF001
        token = await client.exchange_code("code-xyz")
    assert token == "ghp_xxx"
    call = post_mock.call_args
    # Endpoint
    assert call.args[0] == "https://github.com/login/oauth/access_token"
    # Form data
    data = call.kwargs["data"]
    assert data["code"] == "code-xyz"
    assert "client_id" in data
    assert "client_secret" in data
    # Accept JSON
    assert call.kwargs["headers"]["Accept"] == "application/json"


@pytest.mark.asyncio
async def test_exchange_code_raises_when_no_token(stubbed_env: None) -> None:
    """GitHub renvoie 200 mais pas de access_token (ex: bad_verification_code)."""
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(
        200,
        json={"error": "bad_verification_code"},
        request=httpx.Request("POST", "https://github.com/login/oauth/access_token"),
    )
    with patch.object(client._http, "post", new=AsyncMock(return_value=fake_resp)):  # noqa: SLF001
        with pytest.raises(ValueError, match="no access_token"):
            await client.exchange_code("bad")


@pytest.mark.asyncio
async def test_get_user_info_passes_bearer_and_returns_login(stubbed_env: None) -> None:
    from role_builder.services.github_publish.oauth import GitHubOAuthClient

    client = GitHubOAuthClient()
    fake_resp = httpx.Response(
        200,
        json={"login": "alice", "id": 42, "name": "Alice"},
        request=httpx.Request("GET", "https://api.github.com/user"),
    )
    with patch.object(client._http, "get", new=AsyncMock(return_value=fake_resp)) as get_mock:  # noqa: SLF001
        info = await client.get_user_info("ghp_xxx")
    assert info["login"] == "alice"
    call = get_mock.call_args
    assert call.args[0] == "https://api.github.com/user"
    assert call.kwargs["headers"]["Authorization"] == "Bearer ghp_xxx"
    assert call.kwargs["headers"]["Accept"] == "application/vnd.github+json"
