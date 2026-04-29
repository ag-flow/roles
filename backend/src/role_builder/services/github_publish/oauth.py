"""Client OAuth GitHub : exchange code, get user info.

Le state CSRF n'est pas géré ici (cf. db_helpers.oauth_states). Cette
classe encapsule uniquement les appels HTTP vers GitHub.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx
import structlog

from role_builder.config import settings

log = structlog.get_logger(__name__)


class GitHubOAuthClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(timeout=30.0)

    def build_authorize_url(self, state: str) -> str:
        params = {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": settings.github_oauth_scope,
            "state": state,
        }
        return f"https://github.com/login/oauth/authorize?{urlencode(params)}"

    async def exchange_code(self, code: str) -> str:
        """Exchange code → access_token. Lève httpx.HTTPStatusError sur erreur."""
        resp = await self._http.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": settings.github_oauth_client_id,
                "client_secret": settings.github_oauth_client_secret,
                "code": code,
                "redirect_uri": settings.github_oauth_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        body = resp.json()
        if "access_token" not in body:
            raise ValueError(f"GitHub returned no access_token: {body}")
        return str(body["access_token"])

    async def get_user_info(self, access_token: str) -> dict:
        resp = await self._http.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    async def aclose(self) -> None:
        await self._http.aclose()


# Singleton consommé par les routes
gh_oauth = GitHubOAuthClient()
