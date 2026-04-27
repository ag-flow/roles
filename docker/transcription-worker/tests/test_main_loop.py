"""Tests pour worker.main — process_job, handle_error, build_provider."""
from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
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


@pytest.fixture()
def patched_calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """Patch download_audio, upload_transcript et helpers db dans worker.main.

    Retourne un dict 'calls' qui collecte tous les appels pour vérif aval.
    """
    from worker import main as wm

    calls: dict[str, list[Any]] = {
        "download": [], "upload": [], "mark_done": [],
        "mark_failed": [], "update_item": [],
        "lookup_project": [], "insert_chunking_job": [],
    }

    def fake_download(s3_key: str, dest: Path) -> None:
        calls["download"].append((s3_key, dest))
        Path(dest).write_bytes(b"fake-audio")

    def fake_upload(s3_key: str, payload: dict[str, Any]) -> None:
        calls["upload"].append((s3_key, payload))

    async def fake_mark_done(job_id: Any, **kwargs: Any) -> None:
        calls["mark_done"].append({"job_id": job_id, **kwargs})

    async def fake_mark_failed(job_id: Any, **kwargs: Any) -> None:
        calls["mark_failed"].append({"job_id": job_id, **kwargs})

    async def fake_update_item(item_id: Any, key: str, **kwargs: Any) -> None:
        calls["update_item"].append({"item_id": item_id, "key": key})

    async def fake_lookup(item_id: Any, *, pool: Any) -> dict[str, Any] | None:
        calls["lookup_project"].append(item_id)
        return {
            "role_project_id": uuid4(),
            "tenant_id": uuid4(),
        }

    async def fake_insert_chunking(
        *,
        source_item_id: Any,
        role_project_id: Any,
        tenant_id: Any,
        transcript_s3_key: str,
        pool: Any,
    ) -> Any:
        calls["insert_chunking_job"].append({
            "source_item_id": source_item_id,
            "role_project_id": role_project_id,
            "tenant_id": tenant_id,
            "transcript_s3_key": transcript_s3_key,
        })
        return uuid4()

    monkeypatch.setattr(wm, "download_audio", fake_download)
    monkeypatch.setattr(wm, "upload_transcript", fake_upload)
    monkeypatch.setattr(wm, "mark_job_done", fake_mark_done)
    monkeypatch.setattr(wm, "mark_job_failed", fake_mark_failed)
    monkeypatch.setattr(wm, "update_source_item_to_transcribed", fake_update_item)
    monkeypatch.setattr(wm, "lookup_role_project_for_item", fake_lookup)
    monkeypatch.setattr(wm, "insert_chunking_job", fake_insert_chunking)
    return calls


async def test_process_job_chains_download_transcribe_upload_mark_done(
    patched_calls: dict[str, list[Any]],
) -> None:
    """process_job exécute download → transcribe → upload → mark_done → update_item."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/podcast/abc.mp3",
        "language": "fr",
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    # Download appelé une fois avec le bon s3_key
    assert len(patched_calls["download"]) == 1
    assert patched_calls["download"][0][0] == "corpus-audio/podcast/abc.mp3"
    # Transcribe appelé avec le path local et le language du job
    assert len(provider.transcribe_calls) == 1
    assert provider.transcribe_calls[0]["language"] == "fr"
    # Upload appelé une fois
    assert len(patched_calls["upload"]) == 1
    # mark_job_done appelé une fois
    assert len(patched_calls["mark_done"]) == 1
    assert patched_calls["mark_done"][0]["provider_used"] == "openai-whisper"
    # update_source_item_to_transcribed appelé une fois
    assert len(patched_calls["update_item"]) == 1
    assert patched_calls["update_item"][0]["item_id"] == job["source_item_id"]


async def test_process_job_computes_transcript_s3_key(
    patched_calls: dict[str, list[Any]],
) -> None:
    """transcript_s3_key = audio_s3_key avec corpus-audio→corpus-transcripts + .json."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/yt/2026/abc.mp3",
        "language": None,
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    expected_key = "corpus-transcripts/yt/2026/abc.json"
    upload_key, _payload = patched_calls["upload"][0]
    assert upload_key == expected_key
    assert patched_calls["mark_done"][0]["result_s3_key"] == expected_key
    assert patched_calls["update_item"][0]["key"] == expected_key


async def test_process_job_injects_cost_estimate_in_metadata(
    patched_calls: dict[str, list[Any]],
) -> None:
    """process_job ajoute cost_estimate_usd dans pivot.metadata avant l'upload."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/x.mp3",
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


async def test_handle_error_402_classifies_exhausted_and_marks_failed(
    patched_calls: dict[str, list[Any]],
) -> None:
    """handle_error sur HTTPStatusError 402 (insufficient_quota) → mark_job_failed
    avec error_history_entry de catégorie 'exhausted'."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/x.mp3",
        "language": None,
        "worker_pool_id": "user_abc",
    }
    provider = _StubProvider()

    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    response = httpx.Response(
        status_code=402,
        json={"error": {"code": "insufficient_quota", "message": "quota exhausted"}},
        request=request,
    )
    exc = httpx.HTTPStatusError("402", request=request, response=response)

    await wm.handle_error(job, provider, exc, pool=object(), settings=wm.settings)

    assert len(patched_calls["mark_failed"]) == 1
    failed = patched_calls["mark_failed"][0]
    assert failed["job_id"] == job["id"]
    entry = failed["error_history_entry"]
    assert entry["category"] == "exhausted"
    assert "quota" in entry["message"].lower()


async def test_handle_error_generic_exception_marks_failed_unknown_or_transient(
    patched_calls: dict[str, list[Any]],
) -> None:
    """Sur exception non-HTTP, handle_error mark_job_failed avec category transient/unknown."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_s3_key": "corpus-audio/x.mp3",
        "language": None,
        "worker_pool_id": "shared_default",
    }
    provider = _StubProvider()

    await wm.handle_error(
        job, provider, RuntimeError("boom"), pool=object(), settings=wm.settings,
    )

    assert len(patched_calls["mark_failed"]) == 1
    failed = patched_calls["mark_failed"][0]
    entry = failed["error_history_entry"]
    assert entry["category"] in ("transient", "unknown")
    assert "boom" in entry["message"]


async def test_process_job_inserts_chunking_job_after_mark_done(
    patched_calls: dict[str, list[Any]],
) -> None:
    """Sprint 4 : après mark_job_done, le worker enchaîne insert_chunking_job."""
    from worker import main as wm

    item_id = uuid4()
    job = {
        "id": uuid4(),
        "source_item_id": item_id,
        "audio_s3_key": "corpus-audio/yt/podcast/abc.mp3",
        "language": "fr",
    }
    provider = _StubProvider()

    await wm.process_job(job, provider, pool=object(), settings=wm.settings)

    # mark_done puis lookup puis insert
    assert len(patched_calls["mark_done"]) == 1
    assert patched_calls["lookup_project"] == [item_id]
    assert len(patched_calls["insert_chunking_job"]) == 1
    inserted = patched_calls["insert_chunking_job"][0]
    assert inserted["source_item_id"] == item_id
    assert inserted["transcript_s3_key"] == "corpus-transcripts/yt/podcast/abc.json"


def test_build_provider_returns_correct_class_or_raises() -> None:
    """build_provider dispatch sur 'openai-whisper'/'faster-whisper' et raise sinon."""
    from worker.config import Settings
    from worker.main import build_provider
    from worker.providers.openai_whisper import OpenAIWhisperProvider

    s = Settings()  # type: ignore[call-arg]
    s.openai_api_key = "sk-test"

    p = build_provider("openai-whisper", s)
    assert isinstance(p, OpenAIWhisperProvider)

    # faster-whisper instancie un WhisperModel (lourd) → on ne le construit pas ici.
    # On vérifie juste que le nom inconnu raise.
    with pytest.raises(ValueError, match="Unknown provider"):
        build_provider("nonsense", s)
