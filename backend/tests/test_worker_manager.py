"""Tests for services.worker_manager — provisioning Docker + auto-stop loop."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import pytest

# --- Stubs asyncpg pool/conn ----------------------------------------------


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []
        self.fetchval_return: Any = None
        self.fetchrow_return: Any = None
        self.fetch_return: list[Any] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return self.fetchval_return

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return self.fetchrow_return

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return self.fetch_return

    async def execute(self, query: str, *args: Any) -> None:
        self.calls.append(("execute", query, args))


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self._conn)


@pytest.fixture()
def stub_conn() -> _StubConn:
    return _StubConn()


@pytest.fixture()
def stub_pool(stub_conn: _StubConn) -> Any:
    return _StubPool(stub_conn)


# --- Stub asyncio.create_subprocess_exec ----------------------------------


class _StubProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _: bytes | None = None) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    async def wait(self) -> int:
        return self.returncode


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    *,
    stdouts: list[bytes] | None = None,
    returncode: int = 0,
) -> list[list[str]]:
    """Patch asyncio.create_subprocess_exec; return list capturing the cmds called."""
    captured: list[list[str]] = []
    queue = list(stdouts or [])

    async def fake_create(*cmd: str, **_: Any) -> _StubProc:
        captured.append(list(cmd))
        out = queue.pop(0) if queue else b""
        return _StubProc(stdout=out, returncode=returncode)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    return captured


# --- Tests -----------------------------------------------------------------


async def test_ensure_user_workers_running_spawns_delta(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """ensure_user_workers_running spawne (workers_count - actifs) workers."""
    from role_builder.db_helpers import transcription_keys as tk
    from role_builder.services import worker_manager as wm_mod

    user_id = uuid4()
    key_id = uuid4()
    primary = {
        "id": key_id,
        "user_id": user_id,
        "provider": "openai-whisper",
        "workers_count": 3,
        "status": "active",
        "is_primary": True,
        "tenant_id": uuid4(),
    }

    async def fake_get_primary(user_id_: UUID, *, pool: Any) -> dict[str, Any]:
        assert user_id_ == user_id
        return primary

    monkeypatch.setattr(tk, "get_primary_key", fake_get_primary)

    # 0 workers déjà actifs → fetchval = 0
    stub_conn.fetchval_return = 0
    cmds = _patch_subprocess(
        monkeypatch,
        stdouts=[b"container-id-1\n", b"container-id-2\n", b"container-id-3\n"],
    )

    manager = wm_mod.WorkerManager(pool=stub_pool, image_tag="latest")
    spawned = await manager.ensure_user_workers_running(user_id)

    assert spawned == 3
    # 3 docker run + 3 INSERT transcription_workers
    docker_runs = [c for c in cmds if c[:2] == ["docker", "run"]]
    assert len(docker_runs) == 3


async def test_ensure_user_workers_running_no_spawn_when_full(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """ensure_user_workers_running ne spawne rien si N workers actifs == workers_count."""
    from role_builder.db_helpers import transcription_keys as tk
    from role_builder.services import worker_manager as wm_mod

    user_id = uuid4()
    primary = {
        "id": uuid4(),
        "user_id": user_id,
        "provider": "openai-whisper",
        "workers_count": 2,
        "status": "active",
        "is_primary": True,
        "tenant_id": uuid4(),
    }

    async def fake_get_primary(user_id_: UUID, *, pool: Any) -> dict[str, Any]:
        return primary

    monkeypatch.setattr(tk, "get_primary_key", fake_get_primary)

    stub_conn.fetchval_return = 2  # déjà 2 actifs
    cmds = _patch_subprocess(monkeypatch)

    manager = wm_mod.WorkerManager(pool=stub_pool, image_tag="latest")
    spawned = await manager.ensure_user_workers_running(user_id)

    assert spawned == 0
    docker_runs = [c for c in cmds if c[:2] == ["docker", "run"]]
    assert docker_runs == []


async def test_spawn_worker_builds_docker_run_with_env(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """spawn_worker construit `docker run -d --name ... -e WORKER_POOL_ID=... etc`."""
    from role_builder.config import settings
    from role_builder.services import worker_manager as wm_mod

    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)

    user_id = uuid4()
    key = {
        "id": uuid4(),
        "user_id": user_id,
        "provider": "openai-whisper",
        "tenant_id": uuid4(),
        "workers_count": 1,
    }
    cmds = _patch_subprocess(monkeypatch, stdouts=[b"abc123def\n"])

    manager = wm_mod.WorkerManager(pool=stub_pool, image_tag="sha-feedface", host="pve1")
    container_id = await manager.spawn_worker(user_id=user_id, key=key, instance_index=0)

    assert container_id == "abc123def"
    assert len(cmds) == 1
    cmd = cmds[0]
    # Forme générale : docker run -d --name rb-worker-... -e ... image
    assert cmd[0] == "docker"
    assert cmd[1] == "run"
    assert "-d" in cmd
    assert any(c.startswith("rb-worker-") for c in cmd), f"missing --name: {cmd}"
    # Env vars critiques
    joined = " ".join(cmd)
    assert "WORKER_POOL_ID=user_" in joined
    assert "TRANSCRIPTION_PROVIDER=openai-whisper" in joined
    assert "OPENAI_API_KEY=sk-test" in joined
    assert "agflow-transcription-worker:sha-feedface" in cmd


async def test_stop_workers_for_key_calls_docker_stop(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """stop_workers_for_key appelle docker stop pour chaque container_id et UPDATE status."""
    from role_builder.services import worker_manager as wm_mod

    key_id = uuid4()
    user_id = uuid4()
    # Premier fetchrow : SELECT user_id, provider FROM user_transcription_keys WHERE id=$1
    stub_conn.fetchrow_return = {"user_id": user_id, "provider": "openai-whisper"}
    workers = [
        {"id": uuid4(), "container_id": "ctr-1", "container_name": "rb-w-1"},
        {"id": uuid4(), "container_id": "ctr-2", "container_name": "rb-w-2"},
    ]
    stub_conn.fetch_return = workers

    cmds = _patch_subprocess(monkeypatch)
    manager = wm_mod.WorkerManager(pool=stub_pool)
    count = await manager.stop_workers_for_key(key_id)

    assert count == 2
    docker_stops = [c for c in cmds if c[:2] == ["docker", "stop"]]
    assert len(docker_stops) == 2
    assert "ctr-1" in docker_stops[0]
    assert "ctr-2" in docker_stops[1]


async def test_auto_stop_idle_excludes_shared_default(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """auto_stop_idle SELECT exclut worker_pool_id='shared_default'."""
    from role_builder.services import worker_manager as wm_mod

    stub_conn.fetch_return = []  # rien à stopper, on vérifie juste la query
    _patch_subprocess(monkeypatch)
    manager = wm_mod.WorkerManager(pool=stub_pool)
    n = await manager.auto_stop_idle(threshold_seconds=300)

    assert n == 0
    # Le SELECT a bien été émis avec exclusion shared_default
    fetch_calls = [c for c in stub_conn.calls if c[0] == "fetch"]
    assert len(fetch_calls) == 1
    query = fetch_calls[0][1]
    assert "shared_default" in query
    # Et threshold_seconds passé en argument
    assert 300 in fetch_calls[0][2]


async def test_auto_stop_idle_stops_each_returned_worker(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """auto_stop_idle docker stop chaque worker idle expiré et UPDATE status='stopped'."""
    from role_builder.services import worker_manager as wm_mod

    workers = [
        {"id": uuid4(), "container_id": "ctr-A", "container_name": "rb-w-A"},
        {"id": uuid4(), "container_id": "ctr-B", "container_name": "rb-w-B"},
    ]
    stub_conn.fetch_return = workers
    cmds = _patch_subprocess(monkeypatch)

    manager = wm_mod.WorkerManager(pool=stub_pool)
    n = await manager.auto_stop_idle(threshold_seconds=120)

    assert n == 2
    docker_stops = [c for c in cmds if c[:2] == ["docker", "stop"]]
    assert {c[2] for c in docker_stops} == {"ctr-A", "ctr-B"}


async def test_run_auto_stop_loop_exits_on_stop_event(
    monkeypatch: pytest.MonkeyPatch, stub_conn: _StubConn, stub_pool: Any
) -> None:
    """run_auto_stop_loop sort proprement quand stop_event est set."""
    from role_builder.services import worker_manager as wm_mod

    stub_conn.fetch_return = []
    _patch_subprocess(monkeypatch)
    manager = wm_mod.WorkerManager(pool=stub_pool)

    stop = asyncio.Event()
    stop.set()  # déjà set : la boucle ne doit même pas tourner une 2e itération
    await asyncio.wait_for(
        manager.run_auto_stop_loop(stop, period_seconds=0.01),
        timeout=2.0,
    )
