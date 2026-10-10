"""Tests for services.audio_sweeper — balayeur d'orphelins et garde disque.

Fichier autoporteur (convention du dépôt : chaque fichier de test duplique ses
fixtures plutôt que de les partager via conftest.py). Le pool Postgres est un
stub local — ce module n'a besoin que du résultat de la requête sur
`transcription_jobs`, jamais d'un vrai moteur SQL.

La valeur qui porte tout ce fichier : `test_sweeper_keeps_files_of_jobs_still_pending`
pose un fichier VIEUX (donc éligible par l'âge seul) ET référencé par un job
`pending` — s'il disparaissait, le balayeur casserait précisément les retries
que la tâche 4 préserve en gardant l'audio après un échec.
"""

from __future__ import annotations

import datetime as dt
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import structlog

# Deux jours : tout fichier antérieur à cette fenêtre est "vieux" dans les
# tests, quelle que soit la valeur par défaut de audio_orphan_retention_h.
_OLD_AGE_H = 72
_YOUNG_AGE_H = 1


class _StubConn:
    def __init__(self, live_audio_paths: list[str]) -> None:
        self._rows = [{"audio_path": p} for p in live_audio_paths]
        self.fetch_calls: list[tuple[str, tuple[Any, ...]]] = []

    async def fetch(self, query: str, *args: Any) -> list[dict[str, Any]]:
        self.fetch_calls.append((query, args))
        return self._rows


class _StubAcquireCtx:
    def __init__(self, conn: _StubConn) -> None:
        self._conn = conn

    async def __aenter__(self) -> _StubConn:
        return self._conn

    async def __aexit__(self, *_: Any) -> None:
        return None


class _StubPool:
    def __init__(self, live_audio_paths: list[str] | None = None) -> None:
        self.conn = _StubConn(live_audio_paths or [])

    def acquire(self) -> _StubAcquireCtx:
        return _StubAcquireCtx(self.conn)


def _write_file(path: Path, *, age_h: int, now: dt.datetime, content: bytes = b"x") -> None:
    """Crée un fichier et force son mtime à `now - age_h` heures."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    target = (now - dt.timedelta(hours=age_h)).timestamp()
    os.utime(path, (target, target))


async def test_sweeper_removes_files_older_than_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Un fichier plus vieux que audio_orphan_retention_h, sans job vivant,
    est supprimé ; un fichier jeune survit — même en l'absence de toute
    référence. La présence des deux dans le même test est ce qui rend la
    preuve discriminante : un jeu d'essai où tout disparaît ne prouverait
    pas que le filtre d'âge fonctionne."""
    from role_builder.config import settings
    from role_builder.services import audio_sweeper

    monkeypatch.setattr(settings, "audio_volume_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "audio_orphan_retention_h", 48, raising=False)

    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.UTC)
    old_file = tmp_path / "tenant" / "v2" / "src" / "old.mp3"
    young_file = tmp_path / "tenant" / "v2" / "src" / "young.mp3"
    _write_file(old_file, age_h=_OLD_AGE_H, now=now)
    _write_file(young_file, age_h=_YOUNG_AGE_H, now=now)

    pool = _StubPool(live_audio_paths=[])
    deleted = await audio_sweeper.sweep_orphan_audio(now=now, pool=pool)  # type: ignore[arg-type]

    assert deleted == 1
    assert not old_file.exists()
    assert young_file.exists()


async def test_sweeper_keeps_files_of_jobs_still_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valeur discriminante du ticket : un fichier VIEUX mais référencé par un
    transcription_job encore `pending` doit survivre au balayage — sinon le
    balayeur détruit exactement les retries que la tâche 4 a pris soin de
    préserver en gardant l'audio après un échec."""
    from role_builder.config import settings
    from role_builder.services import audio_sweeper

    monkeypatch.setattr(settings, "audio_volume_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "audio_orphan_retention_h", 48, raising=False)

    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.UTC)
    referenced_file = tmp_path / "tenant" / "v2" / "src" / "retry-pending.mp3"
    orphan_file = tmp_path / "tenant" / "v2" / "src" / "orphan.mp3"
    # Les deux sont vieux : seule la référence vivante doit faire la différence.
    _write_file(referenced_file, age_h=_OLD_AGE_H, now=now)
    _write_file(orphan_file, age_h=_OLD_AGE_H, now=now)

    pool = _StubPool(live_audio_paths=[str(referenced_file)])
    deleted = await audio_sweeper.sweep_orphan_audio(now=now, pool=pool)  # type: ignore[arg-type]

    assert deleted == 1
    assert referenced_file.exists()
    assert not orphan_file.exists()
    # La protection vient bien d'un filtre sur les statuts vivants, pas d'un
    # stub qui renverrait n'importe quoi : vérifie l'argument réellement
    # envoyé à la requête SQL.
    query, args = pool.conn.fetch_calls[0]
    assert "transcription_jobs" in query
    assert set(args[0]) == {"pending", "claimed", "processing"}


async def test_sweeper_logs_reclaimed_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """L'espace récupéré est journalisé : sans cette trace, personne ne sait
    si la garde sert encore, et quelqu'un la désactivera « le temps de »."""
    from role_builder.config import settings
    from role_builder.services import audio_sweeper

    monkeypatch.setattr(settings, "audio_volume_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "audio_orphan_retention_h", 48, raising=False)

    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.UTC)
    old_file = tmp_path / "tenant" / "v2" / "src" / "old.mp3"
    _write_file(old_file, age_h=_OLD_AGE_H, now=now, content=b"x" * 1024)

    pool = _StubPool(live_audio_paths=[])
    with structlog.testing.capture_logs() as captured:
        deleted = await audio_sweeper.sweep_orphan_audio(now=now, pool=pool)  # type: ignore[arg-type]

    assert deleted == 1
    decision_logs = [e for e in captured if e.get("event") == "audio_sweeper.orphans_removed"]
    assert len(decision_logs) == 1
    assert decision_logs[0]["deleted"] == 1
    assert decision_logs[0]["reclaimed_bytes"] == 1024


async def test_sweeper_no_candidate_does_not_log_removal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rien à balayer → pas de ligne 'orphans_removed' (une ligne par run
    vide noierait la seule qui compte, cf. skill observability-logs)."""
    from role_builder.config import settings
    from role_builder.services import audio_sweeper

    monkeypatch.setattr(settings, "audio_volume_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "audio_orphan_retention_h", 48, raising=False)

    now = dt.datetime(2026, 10, 10, 12, 0, tzinfo=dt.UTC)
    pool = _StubPool(live_audio_paths=[])
    with structlog.testing.capture_logs() as captured:
        deleted = await audio_sweeper.sweep_orphan_audio(now=now, pool=pool)  # type: ignore[arg-type]

    assert deleted == 0
    assert [e for e in captured if e.get("event") == "audio_sweeper.orphans_removed"] == []


async def test_orchestrator_refuses_new_job_below_min_free_gb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Garde disque fail closed : en dessous de audio_min_free_gb, le job est
    refusé AVANT tout docker run — mieux vaut refuser que remplir le disque
    en silence. `audio_volume_dir` pointe vers un VRAI répertoire (tmp_path)
    pour que `shutil.disk_usage` mesure un espace réel ; `audio_min_free_gb`
    est posé à une valeur absurdement haute pour que le refus soit
    déterministe quel que soit l'espace réellement libre sur la machine de
    test (pas de dépendance à l'état du disque, cf. skill tests)."""
    from role_builder.config import settings
    from role_builder.db_helpers import scraping_jobs as sj
    from role_builder.db_helpers import sources as sm
    from role_builder.services import scraper_orchestrator

    monkeypatch.setattr(settings, "audio_volume_host_dir", "/srv/audio-host", raising=False)
    monkeypatch.setattr(settings, "audio_volume_dir", str(tmp_path), raising=False)
    monkeypatch.setattr(settings, "audio_min_free_gb", 10**9, raising=False)

    mark_failed_calls: list[tuple[Any, str]] = []

    async def fake_mark_processing(job_id: Any, **kw: Any) -> None:
        return None

    async def fake_mark_failed(job_id: Any, error: str, **kw: Any) -> None:
        mark_failed_calls.append((job_id, error))

    async def fake_get_source(*args: Any, **kw: Any) -> None:
        raise AssertionError(
            "get_source ne doit pas être appelé : refus avant résolution de source"
        )

    def _must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("run_container ne doit pas être appelé : garde disque déclenchée")

    monkeypatch.setattr(sj, "mark_job_processing", fake_mark_processing)
    monkeypatch.setattr(sj, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(scraper_orchestrator, "run_container", _must_not_run)

    job = {
        "id": uuid4(),
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": "download",
        "credentials_id": None,
    }
    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")  # type: ignore[arg-type]
    await orch.process_one_job(job)

    assert len(mark_failed_calls) == 1
    failed_job_id, error_msg = mark_failed_calls[0]
    assert failed_job_id == job["id"]
    assert "espace disque" in error_msg


async def test_orchestrator_refuses_job_when_audio_volume_dir_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si `audio_volume_dir` est inaccessible DEPUIS L'ORCHESTRATEUR (montage
    absent côté backend, droits), `shutil.disk_usage` lève — on ne sait alors
    pas s'il reste de la place. Refuser le job plutôt que de laisser passer
    un job sur une garde qu'on ne peut pas vérifier : sinon une exception non
    rattrapée laisserait le job bloqué `processing` pour toujours (pire que
    l'absence de garde), au lieu d'un refus bruyant et visible."""
    from role_builder.config import settings
    from role_builder.db_helpers import scraping_jobs as sj
    from role_builder.db_helpers import sources as sm
    from role_builder.services import scraper_orchestrator

    monkeypatch.setattr(settings, "audio_volume_host_dir", "/srv/audio-host", raising=False)
    # Chemin garanti absent : pas de dépendance à l'état réel du disque.
    monkeypatch.setattr(
        settings, "audio_volume_dir", "/this/path/does/not/exist/ever", raising=False
    )

    mark_failed_calls: list[tuple[Any, str]] = []

    async def fake_mark_processing(job_id: Any, **kw: Any) -> None:
        return None

    async def fake_mark_failed(job_id: Any, error: str, **kw: Any) -> None:
        mark_failed_calls.append((job_id, error))

    async def fake_get_source(*args: Any, **kw: Any) -> None:
        raise AssertionError(
            "get_source ne doit pas être appelé : refus avant résolution de source"
        )

    def _must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("run_container ne doit pas être appelé : garde disque indisponible")

    monkeypatch.setattr(sj, "mark_job_processing", fake_mark_processing)
    monkeypatch.setattr(sj, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(sm, "get_source", fake_get_source)
    monkeypatch.setattr(scraper_orchestrator, "run_container", _must_not_run)

    job = {
        "id": uuid4(),
        "source_id": uuid4(),
        "source_item_id": None,
        "tenant_id": uuid4(),
        "command": "download",
        "credentials_id": None,
    }
    orch = scraper_orchestrator.ScraperOrchestrator(pool=object(), worker_id="w-1")  # type: ignore[arg-type]
    await orch.process_one_job(job)  # ne doit pas lever

    assert len(mark_failed_calls) == 1
    failed_job_id, error_msg = mark_failed_calls[0]
    assert failed_job_id == job["id"]
    assert "garde disque indisponible" in error_msg
