"""Tests for the download command (writes audio into the mounted output.dir)."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

import pytest


class _StubProcess:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return (b"", b"")


def _patch_subprocess_writes_file(monkeypatch: pytest.MonkeyPatch, returncodes: list[int]) -> None:
    """Stub yt-dlp : pop a queued returncode, and on success write fake bytes
    to the '-o' target path -- mimicking what yt-dlp would have produced.
    """
    queue = list(returncodes)

    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        rc = queue.pop(0) if queue else 0
        if rc == 0:
            output_path = Path(args[args.index("-o") + 1])
            output_path.write_bytes(b"fake audio")
        return _StubProcess(rc)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _factory)


def _base_task(output_dir: Path, item_id: str = "v1", prefix: str = "tenant/v2/source/") -> dict[str, Any]:
    return {
        "task_id": "t",
        "items": [{"id": item_id, "url": f"https://youtube.com/watch?v={item_id}"}],
        "options": {"audio_format": "mp3"},
        "output": {"dir": str(output_dir), "prefix": prefix, "format": "mp3"},
    }


@pytest.mark.asyncio
async def test_download_writes_audio_into_output_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Audio lands at output.dir/prefix + item_id.format, and survives the call -- no more MinIO upload-then-delete."""
    output_dir = tmp_path / "volume"
    output_dir.mkdir()
    _patch_subprocess_writes_file(monkeypatch, [0])
    monkeypatch.setattr("sys.stdout", io.StringIO())

    from youtube import download

    rc = await download.run(_base_task(output_dir))
    assert rc == 0

    expected_path = output_dir / "tenant" / "v2" / "source" / "v1.mp3"
    assert expected_path.exists()
    assert expected_path.read_bytes() == b"fake audio"


@pytest.mark.asyncio
async def test_item_done_carries_audio_path_not_s3_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """item_done now points at a filesystem path, the s3_key field is gone."""
    output_dir = tmp_path / "volume"
    output_dir.mkdir()
    _patch_subprocess_writes_file(monkeypatch, [0])
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    rc = await download.run(_base_task(output_dir))
    assert rc == 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    done_event = next(e for e in events if e["type"] == "item_done")
    assert "audio_path" in done_event
    assert "audio_s3_key" not in done_event
    assert done_event["audio_path"] == str(output_dir / "tenant" / "v2" / "source" / "v1.mp3")


@pytest.mark.asyncio
async def test_output_without_dir_emits_error_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Version skew (SCRAPER_IMAGE_TAG pins scraper/backend independently) : a
    payload whose output block lost 'dir' must surface as a readable 'error'
    event -- never an uncaught KeyError crashing the container.
    """
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task: dict[str, Any] = {
        "task_id": "t",
        "items": [{"id": "v1", "url": "https://youtube.com/watch?v=v1"}],
        "output": {"prefix": "tenant/v2/source/", "format": "mp3"},  # no 'dir'
    }
    rc = await download.run(task)
    assert rc != 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    assert events[-1]["type"] == "error"
    assert events[-1]["error"]


@pytest.mark.asyncio
async def test_output_dir_not_writable_fails_before_download(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A read-only output.dir must fail during pre-flight validation, before any yt-dlp invocation is attempted."""
    output_dir = tmp_path / "readonly"
    output_dir.mkdir()
    output_dir.chmod(0o555)  # read + execute only, no write

    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        raise AssertionError("yt-dlp must not be invoked when output.dir is not writable")

    monkeypatch.setattr("asyncio.create_subprocess_exec", _factory)
    monkeypatch.setattr("sys.stdout", io.StringIO())

    from youtube import download

    try:
        rc = await download.run(_base_task(output_dir, prefix="p/"))
    finally:
        output_dir.chmod(0o755)  # restore so tmp_path teardown can remove it

    assert rc != 0


@pytest.mark.asyncio
async def test_replayed_item_does_not_clobber_existing_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Two passes on the same item_id : the second pass writes under a temp
    name and swaps atomically via os.replace, so a reader never observes a
    partially written file at the final path, and the existing file is
    never overwritten in place.
    """
    output_dir = tmp_path / "volume"
    output_dir.mkdir()
    final_path = output_dir / "p" / "v1.mp3"
    final_path.parent.mkdir(parents=True)
    final_path.write_bytes(b"first pass content")

    real_replace = os.replace
    replace_calls: list[tuple[str, str]] = []

    def _spy_replace(src: Any, dst: Any) -> None:
        # At the moment of the swap, the final path still holds the FIRST
        # pass's bytes untouched -- proof the second pass wrote elsewhere first.
        assert final_path.read_bytes() == b"first pass content"
        replace_calls.append((str(src), str(dst)))
        real_replace(src, dst)

    monkeypatch.setattr("os.replace", _spy_replace)
    _patch_subprocess_writes_file(monkeypatch, [0])
    monkeypatch.setattr("sys.stdout", io.StringIO())

    from youtube import download

    rc = await download.run(_base_task(output_dir, prefix="p/"))
    assert rc == 0

    assert len(replace_calls) == 1
    tmp_name, final_name = replace_calls[0]
    assert final_name == str(final_path)
    assert tmp_name != str(final_path)  # distinct temp name, same directory
    assert Path(tmp_name).parent == final_path.parent

    assert final_path.read_bytes() == b"fake audio"  # second pass's content won
    assert list(final_path.parent.iterdir()) == [final_path]  # no leftover temp file


@pytest.mark.asyncio
async def test_disk_full_emits_item_failed_with_message(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """yt-dlp failing (e.g. ENOSPC writing to the volume) must surface as item_failed with a non-empty message."""
    output_dir = tmp_path / "volume"
    output_dir.mkdir()
    _patch_subprocess_writes_file(monkeypatch, [28])  # yt-dlp/ffmpeg exit code observed on ENOSPC
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    rc = await download.run(_base_task(output_dir, prefix="p/"))
    assert rc == 3

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    failed_event = next(e for e in events if e["type"] == "item_failed")
    assert failed_event["item_id"] == "v1"
    assert failed_event["error"]  # message non vide


@pytest.mark.asyncio
async def test_download_emits_complete_with_downloaded_and_failed_counts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    """complete event still aggregates downloaded/failed counts across items."""
    output_dir = tmp_path / "volume"
    output_dir.mkdir()
    _patch_subprocess_writes_file(monkeypatch, [0, 1, 0])
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import download

    task = {
        "task_id": "t",
        "items": [
            {"id": "v1", "url": "u1"},
            {"id": "v2", "url": "u2"},
            {"id": "v3", "url": "u3"},
        ],
        "output": {"dir": str(output_dir), "prefix": "p/", "format": "mp3"},
    }
    rc = await download.run(task)
    assert rc == 3  # partial failure

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    complete = events[-1]
    assert complete == {"type": "complete", "downloaded": 2, "failed": 1}
