"""Client HTTP pour l'API admin ag.flow (création/import/generate-prompts)."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from role_builder.config import settings

log = structlog.get_logger(__name__)

_TIMEOUT = 120.0


class AgflowAdminClient:
    """Client pour `/api/admin/roles/*` d'ag.flow.

    Auth via Bearer token `settings.agflow_api_token` si non-vide.
    Pas d'auth si vide (utile en dev local).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        api_token: str | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self._base_url = base_url if base_url is not None else settings.agflow_base_url
        token = api_token if api_token is not None else getattr(settings, "agflow_api_token", "")
        headers: dict[str, str] = (
            {"Authorization": f"Bearer {token}"} if token else {}
        )
        self._http: Any = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
        )

    async def create_role(
        self,
        *,
        display_name: str,
        description: str | None = None,
    ) -> dict[str, Any]:
        """POST /api/admin/roles. Retourne le rôle créé (avec son `id`)."""
        resp = await self._http.post(
            "/api/admin/roles",
            json={"display_name": display_name, "description": description},
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def import_role_zip(
        self,
        role_id: str,
        zip_bytes: bytes,
    ) -> dict[str, Any]:
        """POST /api/admin/roles/{role_id}/import (multipart)."""
        files = {"file": ("role.zip", zip_bytes, "application/zip")}
        resp = await self._http.post(
            f"/api/admin/roles/{role_id}/import",
            files=files,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def generate_prompts(self, role_id: str) -> dict[str, Any]:
        """POST /api/admin/roles/{role_id}/generate-prompts."""
        resp = await self._http.post(
            f"/api/admin/roles/{role_id}/generate-prompts",
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def get_role(self, role_id: str) -> dict[str, Any]:
        """GET /api/admin/roles/{role_id}."""
        resp = await self._http.get(f"/api/admin/roles/{role_id}")
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def aclose(self) -> None:
        await self._http.aclose()


_client: AgflowAdminClient | None = None


def get_agflow_admin_client() -> AgflowAdminClient:
    """Singleton — réutilise la connexion HTTP."""
    global _client
    if _client is None:
        _client = AgflowAdminClient()
    return _client
