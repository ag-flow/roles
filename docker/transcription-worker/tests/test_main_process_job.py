"""Tests pour worker.main::process_job — lecture de l'audio sur le volume local,
suppression après succès uniquement.

Fichier dédié (plutôt que regroupé dans test_main_loop.py) pour rester sous
la limite de 300 lignes par fichier — même convention que les autres fichiers
de test de ce dépôt (chacun autoporteur, fixtures locales dupliquées plutôt
que partagées via conftest.py).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from worker.pivot import PivotTranscript


class _StubProvider:
    """Provider stub : enregistre les appels transcribe + estimate_cost."""

    name = "openai-whisper"

    def __init__(self, pivot: PivotTranscript | None = None) -> None:
        self._pivot = pivot or PivotTranscript(
            provider="openai-whisper",
            model="whisper-1",
            language="fr",
            language_confidence=None,
            duration_s=120.0,
            segments=[],
            metadata={"transcribed_at": "2026-04-26T10:00:00+00:00"},
        )
        self.transcribe_calls: list[dict[str, Any]] = []

    async def transcribe(
        self, audio_path: str, *, language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        self.transcribe_calls.append({
            "audio_path": audio_path, "language": language, "options": options,
        })
        return self._pivot

    def estimate_cost(self, duration_s: float) -> float:
        return (duration_s / 60.0) * 0.006

    async def get_remaining_credit(self) -> None:
        return None


class _FailingProvider:
    """Provider stub dont `transcribe` échoue toujours — pour le cas échec."""

    name = "openai-whisper"

    def __init__(self, exc: BaseException) -> None:
        self._exc = exc
        self.transcribe_calls: list[dict[str, Any]] = []

    async def transcribe(
        self, audio_path: str, *, language: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> PivotTranscript:
        self.transcribe_calls.append({"audio_path": audio_path})
        raise self._exc

    def estimate_cost(self, duration_s: float) -> float:
        return 0.0

    async def get_remaining_credit(self) -> None:
        return None


@pytest.fixture()
def patched_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Patch upload_transcript et helpers db dans worker.main.

    Retourne un dict 'calls' qui collecte tous les appels pour vérif aval.
    L'audio n'est plus téléchargé (cf. tâche "relais audio volume local") :
    process_job lit directement `job["audio_path"]` sur le disque, il n'y a
    donc plus de fonction `download_audio` à patcher ici.
    """
    from worker import main as wm

    calls: dict[str, list[Any]] = {
        "upload": [], "mark_done": [], "mark_failed": [], "update_item": [],
    }

    def fake_upload(s3_key: str, payload: dict[str, Any]) -> None:
        calls["upload"].append((s3_key, payload))

    async def fake_mark_done(job_id: Any, **kwargs: Any) -> None:
        calls["mark_done"].append({"job_id": job_id, **kwargs})

    async def fake_mark_failed(job_id: Any, **kwargs: Any) -> None:
        calls["mark_failed"].append({"job_id": job_id, **kwargs})

    async def fake_update_item(item_id: Any, key: str, **kwargs: Any) -> None:
        calls["update_item"].append({"item_id": item_id, "key": key})

    monkeypatch.setattr(wm, "upload_transcript", fake_upload)
    monkeypatch.setattr(wm, "mark_job_done", fake_mark_done)
    monkeypatch.setattr(wm, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(wm, "update_source_item_to_transcribed", fake_update_item)
    return calls


def _write_audio(tmp_path: Path, name: str = "abc.mp3") -> Path:
    """Crée un fichier audio réel sous tmp_path, simulant l'écriture du scraper."""
    audio_file = tmp_path / name
    audio_file.write_bytes(b"fake-audio")
    return audio_file


async def test_process_job_reads_audio_from_path_not_minio(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """process_job passe job["audio_path"] tel quel au provider, sans passer
    par MinIO : le module n'expose plus aucune fonction de téléchargement."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path)
    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_path": str(audio_file),
        "language": "fr",
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    assert not hasattr(wm, "download_audio")
    assert len(provider.transcribe_calls) == 1
    assert provider.transcribe_calls[0]["audio_path"] == str(audio_file)


async def test_audio_file_deleted_after_successful_transcription(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """Après un succès complet (mark_done inclus), l'audio est supprimé du
    disque partagé : il a fait son office, le retenir gaspillerait l'espace."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path)
    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_path": str(audio_file),
        "language": None,
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    assert not audio_file.exists()


async def test_audio_file_kept_when_transcription_fails(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """Si la transcription échoue, l'audio reste sur le disque : sinon un
    retry n'aurait plus rien à transcrire. Pas de nettoyage dans un `finally`."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path)
    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_path": str(audio_file),
        "language": None,
    }
    provider = _FailingProvider(RuntimeError("provider boom"))

    with pytest.raises(RuntimeError, match="provider boom"):
        await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    assert audio_file.exists()
    # Aucun des effets de succès n'a eu lieu — l'échec a bien coupé la chaîne
    # avant mark_done, pas seulement avant la suppression.
    assert patched_calls["mark_done"] == []
    assert patched_calls["upload"] == []


async def test_unreadable_audio_file_fails_job_with_path_and_perms(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """Un audio illisible (uid/gid différents entre scraper et worker sur le
    bind mount) fait échouer le job avec un message qui nomme le chemin ET
    les droits — pas un "échec de lecture" générique (Review Focus 3)."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path, "unreadable.mp3")
    audio_file.chmod(0o000)
    try:
        job = {
            "id": uuid4(),
            "source_item_id": uuid4(),
            "audio_path": str(audio_file),
            "language": None,
        }
        provider = _StubProvider()

        with pytest.raises(PermissionError) as exc_info:
            await wm.process_job(job, provider, pool=object(), settings=wm.settings)

        message = str(exc_info.value)
        assert str(audio_file) in message
        assert "droits" in message.lower()
        # Le contrôle de lisibilité précède l'appel au provider.
        assert provider.transcribe_calls == []
        # Conservé : même logique que l'échec de transcription, un retry
        # doit retrouver le fichier une fois les droits corrigés.
        assert audio_file.exists()
    finally:
        audio_file.chmod(0o644)  # restaure pour que tmp_path se nettoie


async def test_process_job_computes_transcript_key_from_source_item_id(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """transcript_s3_key = corpus-transcripts/<source_item_id>.json — plus de
    dérivation depuis la clef audio, qui n'est plus une clef S3."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path)
    source_item_id = uuid4()
    job = {
        "id": uuid4(),
        "source_item_id": source_item_id,
        "audio_path": str(audio_file),
        "language": None,
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    expected_key = f"corpus-transcripts/{source_item_id}.json"
    upload_key, _payload = patched_calls["upload"][0]
    assert upload_key == expected_key
    assert patched_calls["mark_done"][0]["result_s3_key"] == expected_key
    assert patched_calls["update_item"][0]["key"] == expected_key


async def test_process_job_injects_cost_estimate_in_metadata(
    tmp_path: Path, patched_calls: dict[str, list[Any]],
) -> None:
    """process_job ajoute cost_estimate_usd dans pivot.metadata avant l'upload."""
    from worker import main as wm

    audio_file = _write_audio(tmp_path)
    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_path": str(audio_file),
        "language": None,
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    _key, payload = patched_calls["upload"][0]
    # 120s * 0.006/60 = 0.012
    assert payload["metadata"]["cost_estimate_usd"] == pytest.approx(0.012)
    assert "transcribed_at" in payload["metadata"]
    # mark_job_done reçoit la même valeur
    assert patched_calls["mark_done"][0]["cost_estimate_usd"] == pytest.approx(0.012)
