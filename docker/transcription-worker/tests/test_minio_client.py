"""Tests pour worker.minio_client — wrappers download_audio + upload_transcript."""
from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest


class _StubMinio:
    """Stub minimal de minio.Minio pour les tests."""

    def __init__(self) -> None:
        self.fget_calls: list[tuple[str, str, str]] = []
        self.put_calls: list[tuple[str, str, bytes, str | None]] = []

    def fget_object(self, bucket: str, key: str, dest: str) -> None:
        self.fget_calls.append((bucket, key, dest))
        # Simule l'écriture du fichier en local pour permettre les vérifs aval.
        Path(dest).write_bytes(b"fake-audio")

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


def test_download_audio_uses_corpus_audio_bucket_and_writes_dest(
    tmp_path: Path, stub_minio: _StubMinio
) -> None:
    """download_audio appelle fget_object('corpus-audio', s3_key, dest_path)."""
    from worker.minio_client import download_audio

    dest = tmp_path / "x.mp3"
    download_audio("corpus-audio/foo/bar.mp3", dest)

    assert stub_minio.fget_calls == [
        ("corpus-audio", "corpus-audio/foo/bar.mp3", str(dest)),
    ]
    assert dest.exists()
    assert dest.read_bytes() == b"fake-audio"


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
