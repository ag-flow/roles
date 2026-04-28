"""Tests for the OpenBao client."""

from __future__ import annotations

from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any] | None = None) -> None:
        self.status_code = status_code
        self._json = json_body or {}

    def json(self) -> dict[str, Any]:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}")


class _StubHttp:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("POST", url, kwargs))
        return self.next_response or _StubResponse(200)

    async def get(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("GET", url, kwargs))
        return self.next_response or _StubResponse(200, {"data": {"data": {"foo": "bar"}}})

    async def delete(self, url: str, **kwargs: Any) -> _StubResponse:
        self.calls.append(("DELETE", url, kwargs))
        return self.next_response or _StubResponse(204)

    async def aclose(self) -> None: ...


@pytest.mark.asyncio
async def test_put_calls_post_with_data_envelope(stubbed_env: None) -> None:
    """OpenBaoClient.put POSTs to /v1/secret/data/{path} with KV v2 envelope."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    stub = _StubHttp()
    client._http = stub  # type: ignore[assignment]

    await client.put("foo/bar", {"key": "value"})

    method, url, kwargs = stub.calls[0]
    assert method == "POST"
    assert url == "/v1/secret/data/foo/bar"
    assert kwargs["json"] == {"data": {"key": "value"}}


@pytest.mark.asyncio
async def test_get_returns_inner_data(stubbed_env: None) -> None:
    """OpenBaoClient.get returns the inner data dict."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    client._http = _StubHttp()  # type: ignore[assignment]
    result = await client.get("foo/bar")
    assert result == {"foo": "bar"}


@pytest.mark.asyncio
async def test_get_returns_none_on_404(stubbed_env: None) -> None:
    """OpenBaoClient.get returns None when the secret doesn't exist."""
    from role_builder.services.openbao_client import OpenBaoClient

    client = OpenBaoClient()
    stub = _StubHttp()
    stub.next_response = _StubResponse(404)
    client._http = stub  # type: ignore[assignment]
    result = await client.get("missing")
    assert result is None
