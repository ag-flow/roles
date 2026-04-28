"""Tests for services.docker_runner — subprocess docker run + NDJSON streaming."""

from __future__ import annotations

from typing import Any

import pytest


class _StubStdin:
    def __init__(self) -> None:
        self.written: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written.append(data)

    def close(self) -> None:
        self.closed = True


class _StubStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        if not self._lines:
            return b""
        return self._lines.pop(0)


class _StubProc:
    def __init__(self, lines: list[bytes], returncode: int = 0) -> None:
        self.stdin = _StubStdin()
        self.stdout = _StubStdout(lines)
        self.stderr = _StubStdout([])
        self._returncode = returncode

    async def wait(self) -> int:
        return self._returncode


@pytest.fixture()
def patch_subprocess(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch asyncio.create_subprocess_exec; return capture dict for assertions."""
    import asyncio

    capture: dict[str, Any] = {"args": None, "kwargs": None, "proc": None}

    async def fake_exec(*args: Any, **kwargs: Any) -> _StubProc:
        capture["args"] = args
        capture["kwargs"] = kwargs
        return capture["proc"]

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    return capture


async def test_run_container_yields_events_and_exit(
    patch_subprocess: dict[str, Any],
) -> None:
    """Two valid NDJSON lines are yielded as dicts plus a final _exit event."""
    from role_builder.services import docker_runner

    patch_subprocess["proc"] = _StubProc(
        [
            b'{"type": "started", "task_id": "abc"}\n',
            b'{"type": "complete", "downloaded": 2}\n',
        ],
        returncode=0,
    )

    events: list[dict[str, Any]] = []
    async for ev in docker_runner.run_container(
        "agflow-scraper-youtube:latest", env={}, stdin_payload={"command": "discover"}
    ):
        events.append(ev)

    assert len(events) == 3
    assert events[0]["type"] == "started"
    assert events[1]["type"] == "complete"
    assert events[2]["type"] == "_exit"
    assert events[2]["returncode"] == 0


async def test_run_container_yields_invalid_line_on_bad_json(
    patch_subprocess: dict[str, Any],
) -> None:
    """A non-JSON line yields {'type': '_invalid_line', 'raw': ...}."""
    from role_builder.services import docker_runner

    patch_subprocess["proc"] = _StubProc(
        [
            b"this is not json\n",
            b'{"type": "started"}\n',
        ],
        returncode=0,
    )

    events = [
        ev async for ev in docker_runner.run_container("img:latest", env={}, stdin_payload={})
    ]
    assert events[0]["type"] == "_invalid_line"
    assert "this is not json" in events[0]["raw"]
    assert events[1]["type"] == "started"
    assert events[2]["type"] == "_exit"


async def test_run_container_passes_env_args_to_docker_run(
    patch_subprocess: dict[str, Any],
) -> None:
    """create_subprocess_exec receives '-e KEY=value' for each env entry."""
    from role_builder.services import docker_runner

    patch_subprocess["proc"] = _StubProc([], returncode=0)

    [
        ev
        async for ev in docker_runner.run_container(
            "agflow-scraper-youtube:latest",
            env={"FOO": "bar", "MINIO_ENDPOINT": "http://x"},
            stdin_payload={"a": 1},
        )
    ]

    args = patch_subprocess["args"]
    assert args[0] == "docker"
    assert args[1] == "run"
    assert "--rm" in args
    assert "-i" in args
    assert "agflow-scraper-youtube:latest" in args
    # env args present
    args_str = " ".join(str(a) for a in args)
    assert "FOO=bar" in args_str
    assert "MINIO_ENDPOINT=http://x" in args_str
    # stdin payload was JSON-encoded and written
    proc = patch_subprocess["proc"]
    assert proc.stdin.closed is True
    full_stdin = b"".join(proc.stdin.written)
    assert b'"a": 1' in full_stdin or b'"a":1' in full_stdin
