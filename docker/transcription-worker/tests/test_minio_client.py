"""Tests pour worker.minio_client — wrapper upload_transcript.

L'audio n'est plus un objet MinIO (cf. migration 0012 / lot "relais audio
volume local") : il est lu directement sur un volume local partagé par
`worker.main.process_job`. Seul le pivot JSON de sortie reste ici.
"""
from __future__ import annotations

import json
from io import BytesIO
from typing import Any

import pytest


class _StubMinio:
    """Stub minimal de minio.Minio pour les tests."""

    def __init__(self) -> None:
        self.put_calls: list[tuple[str, str, bytes, str | None]] = []

    def put_object(
        self,
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = None,
    ) -> None:
        self.put_calls.append((bucket, key, data.read(), content_type))


@pytest.fixture()
def stub_minio(monkeypatch: pytest.MonkeyPatch) -> _StubMinio:
    """Patch worker.minio_client._build_minio_client pour renvoyer le stub."""
    stub = _StubMinio()
    from worker import minio_client

    monkeypatch.setattr(
        minio_client, "_build_minio_client", lambda: stub
    )
    # Force la recréation du client cached
    monkeypatch.setattr(minio_client, "_client", None, raising=False)
    return stub


def test_upload_transcript_writes_json_to_corpus_transcripts(
    stub_minio: _StubMinio,
) -> None:
    """upload_transcript serialize le payload en JSON et put dans corpus-transcripts."""
    from worker.minio_client import upload_transcript

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "provider": "openai-whisper",
        "duration_s": 12.34,
        "segments": [],
        "metadata": {"transcribed_at": "2026-04-26T10:00:00+00:00"},
    }
    upload_transcript("corpus-transcripts/foo/bar.json", payload)

    assert len(stub_minio.put_calls) == 1
    bucket, key, body, content_type = stub_minio.put_calls[0]
    assert bucket == "corpus-transcripts"
    assert key == "corpus-transcripts/foo/bar.json"
    assert content_type == "application/json"
    assert json.loads(body.decode("utf-8")) == payload


def test_upload_transcript_passes_correct_length(stub_minio: _StubMinio) -> None:
    """upload_transcript fournit length cohérent à minio.put_object (sinon S3 rejette)."""
    from worker import minio_client

    captured: dict[str, int] = {}

    def _capture(
        bucket: str,
        key: str,
        data: BytesIO,
        length: int,
        content_type: str | None = None,
    ) -> None:
        captured["length"] = length
        captured["actual_bytes"] = len(data.getvalue())

    stub_minio.put_object = _capture  # type: ignore[method-assign]
    minio_client.upload_transcript("corpus-transcripts/x.json", {"a": 1})
    assert captured["length"] == captured["actual_bytes"]
