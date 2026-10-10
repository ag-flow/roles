"""Tests pour worker.main — handle_error, build_provider.

Les tests de `process_job` (lecture de l'audio sur le volume local,
suppression après succès) vivent dans test_main_process_job.py — scindé pour
rester sous la limite de 300 lignes par fichier.
"""
from __future__ import annotations

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
    """Patch mark_job_failed dans worker.main pour les tests de handle_error."""
    from worker import main as wm

    calls: dict[str, list[Any]] = {"mark_failed": []}

    async def fake_mark_failed(job_id: Any, **kwargs: Any) -> None:
        calls["mark_failed"].append({"job_id": job_id, **kwargs})

    monkeypatch.setattr(wm, "mark_job_failed", fake_mark_failed)
    return calls


async def test_handle_error_402_classifies_exhausted_and_marks_failed(
    patched_calls: dict[str, list[Any]],
) -> None:
    """handle_error sur HTTPStatusError 402 (insufficient_quota) → mark_job_failed
    avec error_history_entry de catégorie 'exhausted'."""
    from worker import main as wm

    job = {
        "id": uuid4(),
        "source_item_id": uuid4(),
        "audio_path": "/mnt/corpus-audio/x.mp3",
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
        "audio_path": "/mnt/corpus-audio/x.mp3",
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
