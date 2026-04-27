"""Tests for the embedder wrapper around AgflowClient."""
from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_embed_texts_delegates_to_agflow_client(
    stubbed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """embed_texts délègue 1:1 à get_agflow_client().invoke_embeddings."""
    from role_builder.services import agflow_client, embedder

    captured_texts: list[list[str]] = []

    class _StubClient:
        async def invoke_embeddings(self, texts: list[str]) -> list[list[float]]:
            captured_texts.append(texts)
            return [[0.1] * 1024 for _ in texts]

    monkeypatch.setattr(
        agflow_client, "get_agflow_client", lambda: _StubClient(), raising=True
    )

    vectors = await embedder.embed_texts(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == 1024 for v in vectors)
    assert captured_texts == [["a", "b", "c"]]


@pytest.mark.asyncio
async def test_embed_texts_returns_empty_for_empty_input(
    stubbed_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Liste vide → pas d'appel client, retourne []."""
    from role_builder.services import agflow_client, embedder

    called: dict[str, Any] = {"n": 0}

    class _StubClient:
        async def invoke_embeddings(self, texts: list[str]) -> list[list[float]]:
            called["n"] += 1
            return []

    monkeypatch.setattr(
        agflow_client, "get_agflow_client", lambda: _StubClient(), raising=True
    )

    result = await embedder.embed_texts([])
    assert result == []
    assert called["n"] == 0
