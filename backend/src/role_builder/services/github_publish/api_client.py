"""Client REST GitHub : list repos + get/put/delete contents.

Le token bearer est passé au constructeur. Les erreurs HTTP sont remontées
via httpx.HTTPStatusError. Pagination de list_repos jusqu'à un page vide.
"""

from __future__ import annotations

from typing import Any

import httpx


class GitHubApiClient:
    def __init__(self, *, access_token: str) -> None:
        self._http = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github+json",
            },
        )

    async def list_repos(self) -> list[dict[str, Any]]:
        """Liste tous les repos accessibles (pagination par 100)."""
        repos: list[dict[str, Any]] = []
        page = 1
        while True:
            resp = await self._http.get(
                "https://api.github.com/user/repos",
                params={"per_page": 100, "page": page, "sort": "updated"},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            repos.extend(batch)
            page += 1
        return repos

    async def get_content_sha(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str,
    ) -> str | None:
        """Retourne le sha du fichier ou None si 404."""
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            params={"ref": branch},
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def put_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        content_b64: str,
        message: str,
        existing_sha: str | None,
    ) -> str:
        """PUT /contents/{path}. Retourne le commit_sha."""
        body: dict[str, Any] = {
            "message": message,
            "content": content_b64,
            "branch": branch,
        }
        if existing_sha is not None:
            body["sha"] = existing_sha
        resp = await self._http.put(
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            json=body,
        )
        resp.raise_for_status()
        return str(resp.json()["commit"]["sha"])

    async def delete_content(
        self,
        *,
        owner: str,
        repo: str,
        path: str,
        branch: str,
        existing_sha: str,
        message: str,
    ) -> str:
        """DELETE /contents/{path}. Retourne le commit_sha."""
        resp = await self._http.request(
            "DELETE",
            f"https://api.github.com/repos/{owner}/{repo}/contents/{path}",
            json={"message": message, "branch": branch, "sha": existing_sha},
        )
        resp.raise_for_status()
        return str(resp.json()["commit"]["sha"])

    async def aclose(self) -> None:
        await self._http.aclose()
