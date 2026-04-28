"""Tests TDD pour services/agflow/api_client.py (AgflowAdminClient)."""

from __future__ import annotations

from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int = 200, json_body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._body = json_body or {}

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response

            raise HTTPStatusError(
                "fake error",
                request=Request("POST", "http://x"),
                response=Response(status_code=self.status_code),
            )


class _StubAsyncClient:
    def __init__(self, next_response: _StubResponse | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response = next_response or _StubResponse()
        self.headers: dict[str, str] = {}

    async def post(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"method": "POST", "path": path, **kwargs})
        return self.next_response

    async def get(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"method": "GET", "path": path, **kwargs})
        return self.next_response

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_create_role_sends_post(stubbed_env: None) -> None:
    """create_role envoie POST /api/admin/roles avec body display_name + description."""
    from role_builder.services.agflow.api_client import AgflowAdminClient

    stub = _StubAsyncClient(_StubResponse(200, {"id": "role-123", "display_name": "Test"}))
    client = AgflowAdminClient(base_url="http://agflow-test", api_token="")
    client._http = stub  # type: ignore[assignment]

    result = await client.create_role(display_name="Test Role", description="Une description")

    assert result == {"id": "role-123", "display_name": "Test"}
    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/admin/roles"
    assert call["json"]["display_name"] == "Test Role"
    assert call["json"]["description"] == "Une description"


@pytest.mark.asyncio
async def test_import_role_zip_sends_multipart_post(stubbed_env: None) -> None:
    """import_role_zip envoie POST /api/admin/roles/{id}/import avec files multipart."""
    from role_builder.services.agflow.api_client import AgflowAdminClient

    stub = _StubAsyncClient(_StubResponse(200, {"imported": True, "documents_count": 3}))
    client = AgflowAdminClient(base_url="http://agflow-test", api_token="")
    client._http = stub  # type: ignore[assignment]

    zip_bytes = b"PK fake zip content"
    result = await client.import_role_zip("role-abc", zip_bytes)

    assert result == {"imported": True, "documents_count": 3}
    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/admin/roles/role-abc/import"
    assert "files" in call
    assert call["files"]["file"][0] == "role.zip"
    assert call["files"]["file"][1] == zip_bytes


@pytest.mark.asyncio
async def test_generate_prompts_sends_post(stubbed_env: None) -> None:
    """generate_prompts envoie POST /api/admin/roles/{id}/generate-prompts."""
    from role_builder.services.agflow.api_client import AgflowAdminClient

    stub = _StubAsyncClient(_StubResponse(200, {"status": "generating"}))
    client = AgflowAdminClient(base_url="http://agflow-test", api_token="")
    client._http = stub  # type: ignore[assignment]

    await client.generate_prompts("role-xyz")

    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "POST"
    assert call["path"] == "/api/admin/roles/role-xyz/generate-prompts"


@pytest.mark.asyncio
async def test_get_role_sends_get(stubbed_env: None) -> None:
    """get_role envoie GET /api/admin/roles/{id}."""
    from role_builder.services.agflow.api_client import AgflowAdminClient

    stub = _StubAsyncClient(_StubResponse(200, {"id": "role-42", "display_name": "Mon rôle"}))
    client = AgflowAdminClient(base_url="http://agflow-test", api_token="")
    client._http = stub  # type: ignore[assignment]

    result = await client.get_role("role-42")

    assert result["id"] == "role-42"
    assert len(stub.calls) == 1
    call = stub.calls[0]
    assert call["method"] == "GET"
    assert call["path"] == "/api/admin/roles/role-42"


@pytest.mark.asyncio
async def test_auth_bearer_present_when_token_non_empty(stubbed_env: None) -> None:
    """Authorization Bearer présent dans les headers si agflow_api_token non-vide."""
    import httpx

    headers_captured: dict[str, str] = {}

    class _CapturingFactory:
        def __init__(self, base_url: str, timeout: float, headers: dict) -> None:
            headers_captured.update(headers)

        async def post(self, path: str, **kwargs: Any) -> _StubResponse:
            return _StubResponse(200, {"id": "x"})

        async def aclose(self) -> None:
            return None

    from role_builder.services.agflow import api_client as mod

    original_class = httpx.AsyncClient
    mod.httpx.AsyncClient = _CapturingFactory  # type: ignore[assignment]
    try:
        mod.AgflowAdminClient(base_url="http://test", api_token="my-secret-token")
        assert headers_captured.get("Authorization") == "Bearer my-secret-token"
    finally:
        mod.httpx.AsyncClient = original_class  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_no_auth_header_when_token_empty(stubbed_env: None) -> None:
    """Pas d'Authorization header si token vide."""
    import httpx

    headers_captured: dict[str, str] = {}

    class _CapturingFactory:
        def __init__(self, base_url: str, timeout: float, headers: dict) -> None:
            headers_captured.update(headers)

        async def post(self, path: str, **kwargs: Any) -> _StubResponse:
            return _StubResponse(200, {})

        async def aclose(self) -> None:
            return None

    from role_builder.services.agflow import api_client as mod

    original_class = httpx.AsyncClient
    mod.httpx.AsyncClient = _CapturingFactory  # type: ignore[assignment]
    try:
        mod.AgflowAdminClient(base_url="http://test", api_token="")
        assert "Authorization" not in headers_captured
    finally:
        mod.httpx.AsyncClient = original_class  # type: ignore[assignment]
