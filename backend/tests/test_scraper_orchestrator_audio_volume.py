"""Tests for services.scraper_orchestrator — garde-fou audio_volume_host_dir.

Fichier séparé de test_scraper_orchestrator.py (qui approchait la limite de
300 lignes) : couvre spécifiquement le montage du volume audio (`-v`) sur le
`docker run` d'un job et le refus fail-closed quand le host_dir n'est pas
configuré. Duplique localement les fixtures `calls`/`patched`/`_make_runner`
plutôt que de les partager via conftest.py — même convention que les tests
de migration de ce dépôt (chaque fichier de test reste autoporteur).
"""

from __future__ import annotations

import shutil
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest


@pytest.fixture()
def calls() -> dict[str, list[Any]]:
    return {
        "mark_processing": [],
        "mark_done": [],
        "mark_failed": [],
        "get_source": [],
        "handle_event": [],
    }


@pytest.fixture()
def patched(monkeypatch: pytest.MonkeyPatch, calls: dict[str, list[Any]]) -> Any:
    """Patch out db_helpers + handle_scraper_event (docker_runner.run_container
    est patché individuellement par chaque test, ici, puisque le point exact
    de la question — est-il appelé, et avec quoi — varie selon le test)."""
    from role_builder.db_helpers import scraping_jobs as sj
    from role_builder.db_helpers import sources as sm
    from role_builder.services import event_handlers

    async def fake_mark_processing(job_id: Any, **kw: Any) -> None:
        calls["mark_processing"].append(job_id)

    async def fake_mark_done(job_id: Any, **kw: Any) -> None:
        calls["mark_done"].append(job_id)

    async def fake_mark_failed(job_id: Any, error: str, **kw: Any) -> None:
        calls["mark_failed"].append((job_id, error))

    async def fake_get_source(source_id: Any, **kw: Any) -> dict[str, Any]:
        calls["get_source"].append(source_id)
        return {
            "id": source_id,
            "platform": "youtube",
            "url": "https://www.youtube.com/@example",
            "role_project_id": uuid4(),
        }

    async def fake_handle_event(event: dict[str, Any], job: dict[str, Any], **kw: Any) -> None:
        calls["handle_event"].append((event, job))

    monkeypatch.setattr(sj, "mark_job_processing", fake_mark_processing)
    monkeypatch.setattr(sj, "mark_job_done", fake_mark_done)
    monkeypatch.setattr(sj, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(event_handlers, "handle_scraper_event", fake_handle_event)
    return calls


def _make_runner(events: list[dict[str, Any]]) -> Any:
    """Return an async generator factory yielding the given events, capturing
    the kwargs it was called with (notamment `docker_args`)."""

    async def runner(image: str, env: dict[str, str], stdin_payload: dict[str, Any], **kw: Any):
        runner.last_kwargs = kw  # type: ignore[attr-defined]
        for ev in events:
            yield ev

    return runner


def _job(command: str = "download") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": command,
        "credentials_id": None,
    }


async def test_process_one_job_mounts_audio_volume_before_image(
    patched: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le docker run du job monte -v <host_dir>:<container_dir> ; l'ordre
    (avant l'image) est garanti par docker_runner.run_container lui-même,
    cf. test_docker_runner.py::test_run_container_docker_args_precede_image_extra_args_follow."""
    from role_builder.config import settings as _settings
    from role_builder.services import scraper_orchestrator

    monkeypatch.setattr(_settings, "audio_volume_host_dir", "/srv/audio-host", raising=False)
    monkeypatch.setattr(_settings, "audio_volume_dir", "/mnt/corpus-audio", raising=False)
    # Garde disque (tâche 6) : ce test porte sur le montage `-v`, pas sur la
    # garde elle-même (couverte dans test_audio_sweeper.py) — neutraliser
    # shutil.disk_usage plutôt que d'exiger que "/mnt/corpus-audio" existe
    # réellement sur la machine qui exécute les tests.
    monkeypatch.setattr(
        shutil,
        "disk_usage",
        lambda _path: SimpleNamespace(total=0, used=0, free=10**15),
    )

    runner = _make_runner([{"type": "_exit", "returncode": 0}])
    monkeypatch.setattr(scraper_orchestrator, "run_container", runner)

    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")
    await orch.process_one_job(_job())

    docker_args = runner.last_kwargs["docker_args"]  # type: ignore[attr-defined]
    assert docker_args == ["-v", "/srv/audio-host:/mnt/corpus-audio"]


async def test_process_one_job_refuses_when_audio_volume_host_dir_missing(
    patched: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sans audio_volume_host_dir, le job est refusé AVANT de lancer un
    conteneur (fail closed) : sinon l'audio écrit disparaîtrait avec le
    système de fichiers éphémère du scraper, en succès silencieux (BUG-01)."""
    from role_builder.config import settings as _settings
    from role_builder.services import scraper_orchestrator

    monkeypatch.setattr(_settings, "audio_volume_host_dir", "", raising=False)

    def _must_not_be_called(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("run_container ne doit pas être appelé : host_dir manquant")

    monkeypatch.setattr(scraper_orchestrator, "run_container", _must_not_be_called)

    job = _job(command="discover")
    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")
    await orch.process_one_job(job)

    # get_source n'a même pas été appelé : le refus intervient avant toute
    # résolution de source, pas seulement avant le docker run.
    assert patched["get_source"] == []
    assert len(patched["mark_failed"]) == 1
    failed_job_id, error_msg = patched["mark_failed"][0]
    assert failed_job_id == job["id"]
    assert "audio_volume_host_dir" in error_msg
