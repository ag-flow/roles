"""Tests for the NDJSON event emitter."""
from __future__ import annotations

import io
import json

import pytest


def test_emit_writes_single_line_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit writes one NDJSON line to stdout per call."""
    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)

    from youtube.events import emit

    emit("started", task_id="abc")
    emit("progress", item_id="xyz", phase="downloading", percent=42)

    lines = buf.getvalue().strip().split("\n")
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "started", "task_id": "abc"}
    assert json.loads(lines[1]) == {
        "type": "progress",
        "item_id": "xyz",
        "phase": "downloading",
        "percent": 42,
    }


def test_emit_flushes_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    """emit flushes after every line so the orchestrator sees events live."""
    flushed = []

    class _SpyStream:
        def write(self, s: str) -> int:
            return len(s)

        def flush(self) -> None:
            flushed.append(True)

    monkeypatch.setattr("sys.stdout", _SpyStream())

    from youtube.events import emit

    emit("complete", downloaded=10, failed=0)
    assert flushed == [True]
