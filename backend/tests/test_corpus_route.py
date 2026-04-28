"""Tests for routes.corpus — search + chunks + transcript + audio-url."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient


def test_get_search_returns_search_response(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /corpus/search?q=... embed la query puis appelle semantic_search."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    chunk_id = uuid4()
    item_id = uuid4()

    captured: dict[str, Any] = {}

    async def fake_embed(texts: list[str]) -> list[list[float]]:
        captured["embed_texts"] = texts
        return [[0.1, 0.2, 0.3]]

    async def fake_search(**kwargs: Any) -> list[dict[str, Any]]:
        captured["search_kwargs"] = kwargs
        return [
            {
                "chunk_id": chunk_id,
                "source_item_id": item_id,
                "text": "best match",
                "start_s": 0.0,
                "end_s": 10.0,
                "source_title": "Vidéo 1",
                "similarity": 0.9,
            }
        ]

    monkeypatch.setattr(corpus_route.embedder, "embed_texts", fake_embed)
    monkeypatch.setattr(corpus_route.chunks_helper, "semantic_search", fake_search)

    resp = client.get(
        f"/api/role-projects/{project_id}/corpus/search",
        params={"q": "hello", "limit": 5},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["query"] == "hello"
    assert len(body["results"]) == 1
    res0 = body["results"][0]
    assert res0["chunk_id"] == str(chunk_id)
    assert res0["source_item_id"] == str(item_id)
    assert res0["source_title"] == "Vidéo 1"
    assert res0["similarity"] == pytest.approx(0.9)

    assert captured["embed_texts"] == ["hello"]
    assert captured["search_kwargs"]["role_project_id"] == project_id
    assert captured["search_kwargs"]["limit"] == 5
    assert captured["search_kwargs"]["query_embedding"] == [0.1, 0.2, 0.3]


def test_get_search_422_when_query_missing(client: TestClient) -> None:
    """GET /corpus/search sans q → 422 (Pydantic validation)."""
    resp = client.get(f"/api/role-projects/{uuid4()}/corpus/search")
    assert resp.status_code == 422


def test_get_chunks_filters_by_source_item(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /corpus/chunks?source_item_id=... appelle list_by_item."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    item_id = uuid4()
    chunk_id = uuid4()

    captured: dict[str, Any] = {}

    async def fake_list_by_item(
        sid: UUID, *, limit: int, offset: int, pool: Any
    ) -> list[dict[str, Any]]:
        captured["call"] = ("by_item", sid, limit, offset)
        return [
            {
                "id": chunk_id,
                "source_item_id": sid,
                "text": "hello",
                "start_s": 0.0,
                "end_s": 5.0,
            }
        ]

    async def fake_list_by_project(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        captured["called_by_project"] = (args, kwargs)
        return []

    monkeypatch.setattr(corpus_route.chunks_helper, "list_by_item", fake_list_by_item)
    monkeypatch.setattr(corpus_route.chunks_helper, "list_by_project", fake_list_by_project)

    resp = client.get(
        f"/api/role-projects/{project_id}/corpus/chunks",
        params={"source_item_id": str(item_id), "limit": 10, "offset": 0},
    )
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["chunk_id"] == str(chunk_id)
    assert rows[0]["source_item_id"] == str(item_id)
    assert "called_by_project" not in captured

    kind, sid_arg, limit_arg, offset_arg = captured["call"]
    assert kind == "by_item"
    assert sid_arg == item_id
    assert limit_arg == 10
    assert offset_arg == 0


def test_get_chunks_without_source_item_lists_project(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /corpus/chunks sans source_item_id appelle list_by_project."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    chunk_id = uuid4()
    item_id = uuid4()

    captured: dict[str, Any] = {}

    async def fake_list_by_project(
        pid: UUID, *, limit: int, offset: int, pool: Any
    ) -> list[dict[str, Any]]:
        captured["call"] = ("by_project", pid, limit, offset)
        return [
            {
                "id": chunk_id,
                "source_item_id": item_id,
                "source_title": "Titre",
                "text": "hello",
                "start_s": None,
                "end_s": None,
            }
        ]

    async def fake_list_by_item(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        captured["called_by_item"] = (args, kwargs)
        return []

    monkeypatch.setattr(corpus_route.chunks_helper, "list_by_project", fake_list_by_project)
    monkeypatch.setattr(corpus_route.chunks_helper, "list_by_item", fake_list_by_item)

    resp = client.get(f"/api/role-projects/{project_id}/corpus/chunks")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["source_title"] == "Titre"
    assert "called_by_item" not in captured

    kind, pid_arg, limit_arg, offset_arg = captured["call"]
    assert kind == "by_project"
    assert pid_arg == project_id
    assert limit_arg == 50
    assert offset_arg == 0


def test_get_transcript_returns_pivot_json(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /corpus/items/{id}/transcript renvoie le pivot JSON depuis MinIO."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    item_id = uuid4()
    transcript_key = "tenant-x/project-y/item.json"
    pivot_payload = {
        "language": "fr",
        "segments": [{"start": 0.0, "end": 1.0, "text": "Bonjour"}],
    }

    async def fake_get(item_id_arg: UUID, *, pool: Any) -> dict[str, Any]:
        assert item_id_arg == item_id
        return {
            "id": item_id,
            "transcript_s3_key": transcript_key,
            "audio_s3_key": "audio.mp3",
        }

    monkeypatch.setattr(corpus_route.items_helper, "get_by_id", fake_get)

    class _StubMinio:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def download_bytes(self, bucket: str, key: str) -> bytes:
            self.calls.append((bucket, key))
            return json.dumps(pivot_payload).encode("utf-8")

    stub_minio = _StubMinio()
    monkeypatch.setattr(corpus_route.minio_module, "minio_client", stub_minio)

    resp = client.get(f"/api/role-projects/{project_id}/corpus/items/{item_id}/transcript")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["item_id"] == str(item_id)
    assert body["s3_key"] == transcript_key
    assert body["pivot"] == pivot_payload
    assert stub_minio.calls == [("corpus-transcripts", transcript_key)]


def test_get_transcript_404_when_no_transcript_key(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET transcript : 404 si transcript_s3_key est vide (pas encore transcribed)."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    item_id = uuid4()

    async def fake_get(item_id_arg: UUID, *, pool: Any) -> dict[str, Any]:
        return {"id": item_id_arg, "transcript_s3_key": None, "audio_s3_key": None}

    monkeypatch.setattr(corpus_route.items_helper, "get_by_id", fake_get)

    resp = client.get(f"/api/role-projects/{project_id}/corpus/items/{item_id}/transcript")
    assert resp.status_code == 404


def test_get_audio_url_returns_presigned_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET audio-url : appelle presigned_get_url et renvoie l'URL signée."""
    from role_builder.routes import corpus as corpus_route

    project_id = uuid4()
    item_id = uuid4()
    audio_key = "tenant-x/project-y/item.mp3"
    signed_url = "https://minio/example?signature=abc"

    async def fake_get(item_id_arg: UUID, *, pool: Any) -> dict[str, Any]:
        return {
            "id": item_id_arg,
            "audio_s3_key": audio_key,
            "transcript_s3_key": None,
        }

    monkeypatch.setattr(corpus_route.items_helper, "get_by_id", fake_get)

    class _StubMinio:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def presigned_get_url(self, bucket: str, key: str, *, expires_seconds: int) -> str:
            self.calls.append({"bucket": bucket, "key": key, "expires_seconds": expires_seconds})
            return signed_url

    stub_minio = _StubMinio()
    monkeypatch.setattr(corpus_route.minio_module, "minio_client", stub_minio)

    resp = client.get(f"/api/role-projects/{project_id}/corpus/items/{item_id}/audio-url")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["item_id"] == str(item_id)
    assert body["url"] == signed_url
    assert body["expires_in_s"] == 900
    assert stub_minio.calls == [
        {"bucket": "corpus-audio", "key": audio_key, "expires_seconds": 900}
    ]
