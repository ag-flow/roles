"""Tests for the MinIO upload helper inside the scraper container."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest


class _StubMinio:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def fput_object(self, bucket: str, key: str, file_path: str, content_type: str = "application/octet-stream") -> None:
        self.calls.append({"bucket": bucket, "key": key, "file_path": file_path, "content_type": content_type})


@pytest.fixture()
def stub_minio(monkeypatch: pytest.MonkeyPatch) -> _StubMinio:
    stub = _StubMinio()
    monkeypatch.setattr("youtube.minio_uploader._build_client", lambda cfg: stub)
    return stub


def test_upload_audio_writes_to_correct_key(tmp_path: Path, stub_minio: _StubMinio) -> None:
    """upload_audio composes prefix + item_id + .mp3."""
    audio = tmp_path / "v1.mp3"
    audio.write_bytes(b"x" * 1024)

    from youtube import minio_uploader

    cfg = {
        "endpoint": "http://minio:9000",
        "bucket": "corpus-audio",
        "prefix": "tenant/role/source/",
        "access_key": "k",
        "secret_key": "s",
    }
    s3_key = minio_uploader.upload_audio(audio, cfg, item_id="v1")

    assert s3_key == "tenant/role/source/v1.mp3"
    assert stub_minio.calls == [{
        "bucket": "corpus-audio",
        "key": "tenant/role/source/v1.mp3",
        "file_path": str(audio),
        "content_type": "audio/mpeg",
    }]


def test_upload_audio_handles_prefix_without_trailing_slash(
    tmp_path: Path, stub_minio: _StubMinio,
) -> None:
    """A prefix without trailing slash still produces a valid key."""
    audio = tmp_path / "v2.mp3"
    audio.write_bytes(b"x")

    from youtube import minio_uploader

    cfg = {"endpoint": "x", "bucket": "b", "prefix": "tenant/role/source",
           "access_key": "k", "secret_key": "s"}
    s3_key = minio_uploader.upload_audio(audio, cfg, item_id="v2")
    assert s3_key == "tenant/role/source/v2.mp3"
