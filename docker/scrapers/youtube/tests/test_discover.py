"""Tests for the discover command (channel/playlist enumeration)."""
from __future__ import annotations

import io
import json
from typing import Any

import pytest


class _StubProcess:
    def __init__(self, stdout_lines: list[str], returncode: int = 0) -> None:
        self._stdout = stdout_lines
        self.returncode = returncode

    async def communicate(self) -> tuple[bytes, bytes]:
        return ("\n".join(self._stdout).encode(), b"")


async def _make_subprocess(stdout_lines: list[str], returncode: int = 0) -> Any:
    async def _factory(*args: Any, **kwargs: Any) -> _StubProcess:
        return _StubProcess(stdout_lines, returncode)

    return _factory


@pytest.mark.asyncio
async def test_discover_emits_discovered_event_with_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """discover.run parses yt-dlp output and emits a 'discovered' event."""
    stdout_lines = [
        json.dumps({"id": "v1", "title": "Vidéo 1", "duration": 612, "upload_date": "20240101", "thumbnail": "http://t/v1.jpg"}),
        json.dumps({"id": "v2", "title": "Vidéo 2", "duration": 320, "upload_date": "20240115", "thumbnail": "http://t/v2.jpg"}),
    ]
    factory = await _make_subprocess(stdout_lines, returncode=0)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    task = {
        "task_id": "t-1",
        "url": "https://youtube.com/@Channel",
        "options": {"max_items": 100, "since_date": None},
    }
    rc = await discover.run(task)
    assert rc == 0

    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    discovered = next(e for e in events if e["type"] == "discovered")
    assert discovered["total"] == 2
    assert discovered["items"][0]["id"] == "v1"
    assert discovered["items"][0]["duration_s"] == 612
    assert discovered["items"][0]["published_at"] == "2024-01-01T00:00:00Z"
    assert discovered["items"][0]["thumbnail_url"] == "http://t/v1.jpg"


@pytest.mark.asyncio
async def test_discover_emits_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover.run emits 'complete' after listing."""
    factory = await _make_subprocess([json.dumps({"id": "v1", "title": "T", "duration": 60})], returncode=0)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    rc = await discover.run({"task_id": "t-2", "url": "https://yt.com/c", "options": {}})
    assert rc == 0
    events = [json.loads(line) for line in buf.getvalue().strip().split("\n")]
    assert events[-1] == {"type": "complete", "discovered": 1}


@pytest.mark.asyncio
async def test_discover_returns_2_on_yt_dlp_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """discover.run returns exit code 2 when yt-dlp exits non-zero."""
    factory = await _make_subprocess(["[]"], returncode=1)
    monkeypatch.setattr("asyncio.create_subprocess_exec", factory)

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube import discover

    rc = await discover.run({"task_id": "t-3", "url": "https://yt.com/c", "options": {}})
    assert rc == 2
