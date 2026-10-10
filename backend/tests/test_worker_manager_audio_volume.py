"""Tests for services.worker_manager — garde-fou audio_volume_host_dir.

Fichier séparé de test_worker_manager.py (déjà à la limite de 300 lignes) :
couvre spécifiquement le montage du volume audio (`-v`) sur le `docker run -d`
d'un worker, et le refus fail-closed quand le host_dir n'est pas configuré.
Duplique localement les fixtures stub plutôt que de les partager via
conftest.py — même convention que test_scraper_orchestrator_audio_volume.py.

Rappel du relais (lot "relais audio volume local") : le scraper (producteur)
et ce worker (consommateur) doivent chacun monter le MÊME host_dir sur le
MÊME chemin conteneur pour que `job["audio_path"]`, écrit par l'un, résolve
vers un fichier réel chez l'autre. scraper_orchestrator.py monte déjà sa
moitié (tâche 3) ; ce fichier couvre la moitié symétrique côté worker.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import pytest


class _StubConn:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, tuple[Any, ...]]] = []

    async def fetchval(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchval", query, args))
        return 0

    async def fetchrow(self, query: str, *args: Any) -> Any:
        self.calls.append(("fetchrow", query, args))
        return None

    async def fetch(self, query: str, *args: Any) -> list[Any]:
        self.calls.append(("fetch", query, args))
        return []

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


class _StubProc:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0) -> None:
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, _: bytes | None = None) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr


def _patch_subprocess(
    monkeypatch: pytest.MonkeyPatch, *, stdouts: list[bytes] | None = None,
) -> list[list[str]]:
    """Patch asyncio.create_subprocess_exec ; retourne les cmds capturées."""
    captured: list[list[str]] = []
    queue = list(stdouts or [])

    async def fake_create(*cmd: str, **_: Any) -> _StubProc:
        captured.append(list(cmd))
        out = queue.pop(0) if queue else b""
        return _StubProc(stdout=out)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    return captured


async def test_spawn_worker_mounts_audio_volume_before_image(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """spawn_worker ajoute `-v <audio_volume_host_dir>:<audio_volume_dir>`
    avant le nom de l'image — symétrique au montage déjà posé côté scraper."""
    from role_builder.config import settings
    from role_builder.services import worker_manager as wm_mod

    monkeypatch.setattr(settings, "audio_volume_host_dir", "/srv/audio-host", raising=False)
    monkeypatch.setattr(settings, "audio_volume_dir", "/mnt/corpus-audio", raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test", raising=False)

    conn = _StubConn()
    pool = _StubPool(conn)
    cmds = _patch_subprocess(monkeypatch, stdouts=[b"abc123def\n"])

    user_id = uuid4()
    key = {
        "id": uuid4(), "user_id": user_id, "provider": "openai-whisper",
        "tenant_id": uuid4(), "workers_count": 1,
    }
    manager = wm_mod.WorkerManager(pool=pool, image_tag="latest")
    await manager.spawn_worker(user_id=user_id, key=key, instance_index=0)

    assert len(cmds) == 1
    cmd = cmds[0]
    image = "agflow-transcription-worker:latest"
    assert image in cmd
    v_index = cmd.index("-v")
    assert cmd[v_index + 1] == "/srv/audio-host:/mnt/corpus-audio"
    # -v (et sa valeur) doivent précéder l'image : au-delà, c'est la commande
    # du conteneur, pas une option docker (même piège qu'en tâche 3).
    assert v_index < cmd.index(image)


async def test_spawn_worker_refuses_when_audio_volume_host_dir_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sans audio_volume_host_dir, spawn_worker refuse : aucun `docker run`,
    aucune ligne insérée en base — le worker ne doit jamais démarrer sans
    pouvoir voir l'audio qu'il est censé transcrire."""
    from role_builder.config import settings
    from role_builder.services import worker_manager as wm_mod

    monkeypatch.setattr(settings, "audio_volume_host_dir", "", raising=False)

    conn = _StubConn()
    pool = _StubPool(conn)
    cmds = _patch_subprocess(monkeypatch)

    user_id = uuid4()
    key = {
        "id": uuid4(), "user_id": user_id, "provider": "openai-whisper",
        "tenant_id": uuid4(), "workers_count": 1,
    }
    manager = wm_mod.WorkerManager(pool=pool, image_tag="latest")

    with pytest.raises(RuntimeError, match="audio_volume_host_dir"):
        await manager.spawn_worker(user_id=user_id, key=key, instance_index=0)

    assert cmds == []
    # Aucune ligne transcription_workers insérée : le refus précède toute
    # écriture, pas seulement le docker run.
    assert all(c[0] != "execute" for c in conn.calls)
