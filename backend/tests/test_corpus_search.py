"""Tests for services.corpus_search — RAG helper réutilisable Sprint 5."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest


async def test_find_relevant_chunks_embeds_then_searches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """find_relevant_chunks embed la query puis appelle semantic_search."""
    from role_builder.services import corpus_search

    project_id = uuid4()
    captured: dict[str, Any] = {}

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        captured["embed_texts"] = texts
        return [[0.5, 0.5, 0.5]]

    expected_rows = [
        {
            "chunk_id": uuid4(),
            "source_item_id": uuid4(),
            "text": "match",
            "start_s": 0.0,
            "end_s": 5.0,
            "similarity": 0.9,
        }
    ]

    async def fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        captured["search_kwargs"] = kwargs
        return expected_rows

    monkeypatch.setattr(corpus_search.embedder, "embed_texts", fake_embed)
    monkeypatch.setattr(corpus_search.corpus_chunks, "semantic_search", fake_search)

    sentinel_pool = object()
    rows = await corpus_search.find_relevant_chunks(
        project_id,
        "What is X?",
        top_k=7,
        min_similarity=0.6,
        pool=sentinel_pool,  # type: ignore[arg-type]
    )

    assert rows == expected_rows
    assert captured["embed_texts"] == ["What is X?"]
    assert captured["search_kwargs"]["role_project_id"] == project_id
    assert captured["search_kwargs"]["query_embedding"] == [0.5, 0.5, 0.5]
    assert captured["search_kwargs"]["limit"] == 7
    assert captured["search_kwargs"]["min_similarity"] == 0.6
    assert captured["search_kwargs"]["pool"] is sentinel_pool


async def test_find_relevant_chunks_empty_query_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Query blanche → [] sans toucher embedder ni semantic_search."""
    from role_builder.services import corpus_search

    embed_calls: list[list[str]] = []
    search_calls: list[dict[str, Any]] = []

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        embed_calls.append(texts)
        return [[0.0]]

    async def fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        search_calls.append(kwargs)
        return []

    monkeypatch.setattr(corpus_search.embedder, "embed_texts", fake_embed)
    monkeypatch.setattr(corpus_search.corpus_chunks, "semantic_search", fake_search)

    rows = await corpus_search.find_relevant_chunks(
        uuid4(),
        "   \n\t  ",
        pool=object(),  # type: ignore[arg-type]
    )
    assert rows == []
    assert embed_calls == []
    assert search_calls == []
