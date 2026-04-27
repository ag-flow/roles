"""Tests for the download command."""
from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest


class _StubProcess:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")


def _patch_subprocess(monkeypatch: pytest.MonkeyPatch, returncodes: list[int]) -> None:
    """Patch asyncio.create_subprocess_exec to return queued returncodes."""
    queue = list(returncodes)

    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        rc = queue.pop(0) if queue else 0
        return _StubProcess(rc)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _factory)


def _patch_minio(monkeypatch: pytest.MonkeyPatch, calls: list[dict[str, Any]]) -> None:
    """Patch upload_audio to record calls without doing real upload."""
    def _fake_upload(local_path: Path, output_cfg: dict[str, Any], item_id: str) -> str:
        calls.append({"path": str(local_path), "item_id": item_id, "output": output_cfg})
        return f"{output_cfg['prefix']}{item_id}.mp3"

    monkeypatch.setattr("youtube.minio_uploader.upload_audio", _fake_upload)


def _patch_filesystem(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Make sure the produced file 'exists' so download.run doesn't bail out."""
    real_unlink = Path.unlink

    def _ensure_exists(self: Path, missing_ok: bool = False) -> None:
        if not self.exists():
            self.write_bytes(b"fake audio")
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", _ensure_exists)
    monkeypatch.setattr("youtube.download._tmp_dir", lambda: tmp_path)


@pytest.mark.asyncio
async def test_download_uploads_each_item_and_emits_done(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """download.run downloads each item and uploads to MinIO, emitting item_done."""
    _patch_subprocess(monkeypatch, [0, 0])
    calls: list[dict[str, Any]] = []
    _patch_minio(monkeypatch, calls)
    _patch_filesystem(monkeypatch, tmp_path)

    # Pre-create the expected files
    (tmp_path / "v1.mp3").write_bytes(b"audio1")
    (tmp_path / "v2.mp3").write_bytes(b"audio2")

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-1",
        "items": [
            {"id": "v1", "url": "https://youtube.com/watch?v=v1"},
            {"id": "v2", "url": "https://youtube.com/watch?v=v2"},
        ],
        "options": {"audio_format": "mp3"},
        "output": {
            "type": "minio",
            "endpoint": "http://minio:9000",
            "bucket": "corpus-audio",
            "prefix": "tenant/role/source/",
            "access_key": "k",
            "secret_key": "s",
        },
    }
    rc = await download.run(task)
    assert rc == 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    done_events = [e for e in events if e["type"] == "item_done"]
    assert len(done_events) == 2
    assert done_events[0]["item_id"] == "v1"
    assert done_events[0]["audio_s3_key"] == "tenant/role/source/v1.mp3"

    assert len(calls) == 2
    assert calls[0]["item_id"] == "v1"


@pytest.mark.asyncio
async def test_download_emits_item_failed_on_yt_dlp_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """A non-zero yt-dlp returncode emits item_failed, not item_done."""
    _patch_subprocess(monkeypatch, [1])
    _patch_minio(monkeypatch, [])
    _patch_filesystem(monkeypatch, tmp_path)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-2",
        "items": [{"id": "vbad", "url": "https://yt/watch?v=vbad"}],
        "output": {"type": "minio", "endpoint": "x", "bucket": "b", "prefix": "p/",
                   "access_key": "k", "secret_key": "s"},
    }
    rc = await download.run(task)
    # Partial failure : exit code 3 (cf. spec § Codes de sortie)
    assert rc == 3

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    failed = [e for e in events if e["type"] == "item_failed"]
    assert len(failed) == 1
    assert failed[0]["item_id"] == "vbad"


@pytest.mark.asyncio
async def test_download_emits_complete_with_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """complete event aggregates downloaded/failed counts."""
    _patch_subprocess(monkeypatch, [0, 1, 0])
    _patch_minio(monkeypatch, [])
    _patch_filesystem(monkeypatch, tmp_path)
    (tmp_path / "v1.mp3").write_bytes(b"a")
    (tmp_path / "v3.mp3").write_bytes(b"a")

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t-3",
        "items": [
            {"id": "v1", "url": "u1"},
            {"id": "v2", "url": "u2"},
            {"id": "v3", "url": "u3"},
        ],
        "output": {"type": "minio", "endpoint": "x", "bucket": "b", "prefix": "p/",
                   "access_key": "k", "secret_key": "s"},
    }
    rc = await download.run(task)
    assert rc == 3  # partial failure

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    complete = events[-1]
    assert complete == {"type": "complete", "downloaded": 2, "failed": 1}
