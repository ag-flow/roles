"""Tests for the AgflowClient (Mistral API abstraction)."""
from __future__ import annotations

from typing import Any

import pytest


class _StubResponse:
    def __init__(self, status_code: int, json_body: dict[str, Any]) -> None:
        self.status_code = status_code
        self._body = json_body

    def json(self) -> dict[str, Any]:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from httpx import HTTPStatusError, Request, Response
            raise HTTPStatusError(
                "fake",
                request=Request("POST", "http://x"),
                response=Response(status_code=self.status_code),
            )


class _StubAsyncClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.next_response: _StubResponse | None = None

    async def post(self, path: str, **kwargs: Any) -> _StubResponse:
        self.calls.append({"path": path, **kwargs})
        return self.next_response or _StubResponse(200, {})

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_invoke_embeddings_calls_mistral_embed(stubbed_env: None) -> None:
    """invoke_embeddings POST sur /v1/embeddings avec model + input."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", embed_model="mistral-embed")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(
        200,
        {
            "data": [
                {"embedding": [0.1, 0.2, 0.3], "index": 0},
                {"embedding": [0.4, 0.5, 0.6], "index": 1},
            ],
        },
    )
    client._http = stub  # type: ignore[assignment]

    vectors = await client.invoke_embeddings(["text 1", "text 2"])

    assert vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert stub.calls[0]["path"] == "/v1/embeddings"
    assert stub.calls[0]["json"] == {
        "model": "mistral-embed",
        "input": ["text 1", "text 2"],
    }


@pytest.mark.asyncio
async def test_invoke_chat_returns_content_and_usage(stubbed_env: None) -> None:
    """invoke_chat POST sur /v1/chat/completions et retourne ChatResult."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", chat_model="mistral-large-latest")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(
        200,
        {
            "choices": [{"message": {"content": "Bonjour"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "model": "mistral-large-latest",
        },
    )
    client._http = stub  # type: ignore[assignment]

    result = await client.invoke_chat([{"role": "user", "content": "Salut"}])

    assert result.content == "Bonjour"
    assert result.tokens_input == 10
    assert result.tokens_output == 5
    assert result.model == "mistral-large-latest"
    assert stub.calls[0]["path"] == "/v1/chat/completions"


@pytest.mark.asyncio
async def test_invoke_embeddings_batches_above_32(stubbed_env: None) -> None:
    """Si input > 32, plusieurs appels sont faits (batching)."""
    from role_builder.services.agflow_client import AgflowClient

    client = AgflowClient(api_key="sk-test", embed_model="mistral-embed")
    stub = _StubAsyncClient()
    stub.next_response = _StubResponse(
        200,
        {"data": [{"embedding": [0.1] * 1024, "index": 0}]},
    )
    client._http = stub  # type: ignore[assignment]

    texts = ["t"] * 50  # 50 inputs → 2 batches (32 + 18)
    await client.invoke_embeddings(texts)

    assert len(stub.calls) == 2
    assert len(stub.calls[0]["json"]["input"]) == 32
    assert len(stub.calls[1]["json"]["input"]) == 18
