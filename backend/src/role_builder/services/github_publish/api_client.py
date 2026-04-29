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

    # -----------------------------------------------------------------
    # Git data API (Trees) — pour publier N fichiers en 1 commit atomique.
    # -----------------------------------------------------------------

    async def get_ref_sha(
        self,
        owner: str,
        repo: str,
        branch: str,
    ) -> str:
        """GET /git/ref/heads/{branch} → sha du dernier commit de la branche.

        Lève httpx.HTTPStatusError si la branche n'existe pas (404).
        """
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/ref/heads/{branch}",
        )
        resp.raise_for_status()
        return str(resp.json()["object"]["sha"])

    async def get_commit_tree_sha(
        self,
        owner: str,
        repo: str,
        commit_sha: str,
    ) -> str:
        """GET /git/commits/{sha} → sha du tree racine de ce commit."""
        resp = await self._http.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/commits/{commit_sha}",
        )
        resp.raise_for_status()
        return str(resp.json()["tree"]["sha"])

    async def create_blob(
        self,
        owner: str,
        repo: str,
        *,
        content: str,
        encoding: str = "utf-8",
    ) -> str:
        """POST /git/blobs avec encoding 'utf-8' (texte) ou 'base64' → sha du blob."""
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/blobs",
            json={"content": content, "encoding": encoding},
        )
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def create_tree(
        self,
        owner: str,
        repo: str,
        *,
        base_tree_sha: str,
        items: list[dict[str, Any]],
    ) -> str:
        """POST /git/trees avec base_tree pour merge avec l'existant.

        items = liste de {path, mode='100644', type='blob', sha}.
        Pour supprimer un fichier du tree, passer ``sha: None`` (sérialisé en
        ``null`` dans le JSON envoyé à GitHub) — la combinaison
        ``mode='100644'`` + ``type='blob'`` + ``sha=null`` enlève l'entrée.

        Retourne le sha du nouveau tree.
        """
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees",
            json={"base_tree": base_tree_sha, "tree": items},
        )
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def create_commit(
        self,
        owner: str,
        repo: str,
        *,
        message: str,
        tree_sha: str,
        parent_sha: str,
    ) -> str:
        """POST /git/commits → sha du nouveau commit."""
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/commits",
            json={
                "message": message,
                "tree": tree_sha,
                "parents": [parent_sha],
            },
        )
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def update_ref(
        self,
        owner: str,
        repo: str,
        branch: str,
        *,
        new_sha: str,
        force: bool = False,
    ) -> str:
        """PATCH /git/refs/heads/{branch} → sha du commit pointé."""
        resp = await self._http.patch(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{branch}",
            json={"sha": new_sha, "force": force},
        )
        resp.raise_for_status()
        return str(resp.json()["object"]["sha"])

    async def create_tag(
        self,
        owner: str,
        repo: str,
        *,
        tag: str,
        message: str,
        commit_sha: str,
        tagger_name: str = "Role Builder",
        tagger_email: str = "role-builder@example.invalid",
    ) -> str:
        """POST /git/tags — crée l'objet tag annoté, retourne son sha.

        Cet objet n'est PAS encore visible : il faut appeler ``create_tag_ref``
        derrière pour créer la référence ``refs/tags/{tag}``.
        """
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/tags",
            json={
                "tag": tag,
                "message": message,
                "object": commit_sha,
                "type": "commit",
                "tagger": {
                    "name": tagger_name,
                    "email": tagger_email,
                },
            },
        )
        resp.raise_for_status()
        return str(resp.json()["sha"])

    async def create_tag_ref(
        self,
        owner: str,
        repo: str,
        *,
        tag: str,
        tag_sha: str,
    ) -> str:
        """POST /git/refs avec ref=refs/tags/{tag} → expose le tag annoté."""
        resp = await self._http.post(
            f"https://api.github.com/repos/{owner}/{repo}/git/refs",
            json={"ref": f"refs/tags/{tag}", "sha": tag_sha},
        )
        resp.raise_for_status()
        return str(resp.json()["object"]["sha"])

    async def aclose(self) -> None:
        await self._http.aclose()
