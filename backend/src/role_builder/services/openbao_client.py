"""Async client for OpenBao KV v2 secrets engine."""
from __future__ import annotations

import httpx

from role_builder.config import settings


class OpenBaoClient:
    """Minimal async wrapper around OpenBao KV v2 HTTP API."""

    def __init__(self) -> None:
        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=settings.openbao_url,
            headers={"X-Vault-Token": settings.openbao_token},
            timeout=10.0,
        )

    async def put(self, path: str, data: dict[str, object]) -> None:
        """Store a secret at `secret/data/{path}` using the KV v2 envelope."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.post(url, json={"data": data})
        resp.raise_for_status()

    async def get(self, path: str) -> dict[str, object] | None:
        """Read a secret. Returns None if it doesn't exist (404)."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.get(url)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        body = resp.json()
        return body["data"]["data"]

    async def delete(self, path: str) -> None:
        """Soft-delete the latest version of a secret."""
        url = f"/v1/secret/data/{path}"
        resp = await self._http.delete(url)
        if resp.status_code not in (200, 204):
            resp.raise_for_status()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        await self._http.aclose()


openbao = OpenBaoClient()
